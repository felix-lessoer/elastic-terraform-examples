import { constants } from 'node:fs';
import { access, readFile, stat, unlink, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { readDeploymentConfig, repoRoot } from './config.js';
import { executeCommand, type LogWriter } from './run-manager.js';
import { readPrivateTerraformOutput } from './terraform.js';

const toolDirectory = path.join(repoRoot, 'tools/aws-poc-ui');
const dataDirectory = path.join(toolDirectory, '.elastic-poc');
const manifestPath = path.join(dataDirectory, 'manifest.json');
const analysisPath = path.join(dataDirectory, 'analysis.json');
const visibilitySelectionPath = path.join(
  dataDirectory,
  'visibility-selection.json',
);
const visibilityAdapterStatePath = path.join(
  dataDirectory,
  'visibility-adapter-state.json',
);

interface VisibilityProposal {
  id: string;
  resource_arn: string;
  resource_name: string;
  resource_type: string;
  signal: string;
  priority: number;
  change_summary: string;
  prerequisites: string[];
  cost_dimensions: string[];
  validation: string[];
  rollback: string[];
}

export interface VisibilityOption {
  id: string;
  title: string;
  signal: string;
  resourceType: string;
  affectedResources: number;
  recommendedCanary: VisibilityProposal;
  adapter: {
    available: boolean;
    label: string;
  };
}

export interface VisibilityApproval {
  ownerApproved: boolean;
  costReviewed: boolean;
  rollbackReviewed: boolean;
}

async function exists(filePath: string): Promise<boolean> {
  try {
    await access(filePath, constants.F_OK);
    return true;
  } catch {
    return false;
  }
}

async function summary(filePath: string): Promise<{
  modifiedAt: string;
  summary: Record<string, unknown>;
  limitations: string[];
} | null> {
  if (!(await exists(filePath))) return null;
  const [contents, fileStat] = await Promise.all([
    readFile(filePath, 'utf8'),
    stat(filePath),
  ]);
  const parsed = JSON.parse(contents) as {
    summary?: Record<string, unknown>;
    limitations?: string[];
  };
  return {
    modifiedAt: fileStat.mtime.toISOString(),
    summary: parsed.summary ?? {},
    limitations: parsed.limitations ?? [],
  };
}

export async function brownfieldStatus() {
  return {
    manifest: await summary(manifestPath),
    analysis: await summary(analysisPath),
  };
}

async function readProposals(): Promise<VisibilityProposal[]> {
  if (!(await exists(analysisPath))) return [];
  const parsed = JSON.parse(await readFile(analysisPath, 'utf8')) as {
    proposals?: VisibilityProposal[];
  };
  return Array.isArray(parsed.proposals) ? parsed.proposals : [];
}

async function readVisibilitySelection(): Promise<{
  selectedProposalIds: string[];
  approvals: Record<string, VisibilityApproval>;
  deployedProposalIds: string[];
}> {
  if (!(await exists(visibilitySelectionPath))) {
    return { selectedProposalIds: [], approvals: {}, deployedProposalIds: [] };
  }
  const parsed = JSON.parse(await readFile(visibilitySelectionPath, 'utf8')) as {
    selectedProposalIds?: unknown;
    approvals?: unknown;
    deployedProposalIds?: unknown;
  };
  const selectedProposalIds = Array.isArray(parsed.selectedProposalIds)
    ? parsed.selectedProposalIds.filter(
        (id): id is string => typeof id === 'string',
      )
    : [];
  const approvals: Record<string, VisibilityApproval> = {};
  if (
    parsed.approvals &&
    typeof parsed.approvals === 'object' &&
    !Array.isArray(parsed.approvals)
  ) {
    for (const [id, value] of Object.entries(parsed.approvals)) {
      if (value && typeof value === 'object' && !Array.isArray(value)) {
        const approval = value as Partial<VisibilityApproval>;
        approvals[id] = {
          ownerApproved: approval.ownerApproved === true,
          costReviewed: approval.costReviewed === true,
          rollbackReviewed: approval.rollbackReviewed === true,
        };
      }
    }
  }
  const deployedProposalIds = Array.isArray(parsed.deployedProposalIds)
    ? parsed.deployedProposalIds.filter(
        (id): id is string => typeof id === 'string',
      )
    : [];
  return { selectedProposalIds, approvals, deployedProposalIds };
}

const optionTitle = (resourceType: string, signal: string): string => {
  const titles: Record<string, string> = {
    'aws.lambda.function:logs': 'Collect existing Lambda logs',
    'aws.lambda.function:traces': 'Canary Lambda distributed tracing',
    'aws.ecs.service:traces': 'Canary ECS distributed tracing',
    'aws.eks.cluster:metrics': 'Deploy scoped Kubernetes visibility',
    'aws.rds.instance:database': 'Enable deeper RDS visibility',
  };
  return titles[`${resourceType}:${signal}`] ?? `Expand ${signal} visibility`;
};

export async function visibilityExpansionStatus(): Promise<{
  options: VisibilityOption[];
  selectedProposalIds: string[];
  approvals: Record<string, VisibilityApproval>;
  deployedProposalIds: string[];
}> {
  const proposals = await readProposals();
  const grouped = new Map<string, VisibilityProposal[]>();
  for (const proposal of proposals) {
    const key = `${proposal.resource_type}:${proposal.signal}`;
    grouped.set(key, [...(grouped.get(key) ?? []), proposal]);
  }
  const options = [...grouped.entries()]
    .map(([id, items]) => {
      items.sort(
        (left, right) =>
          right.priority - left.priority ||
          left.resource_name.localeCompare(right.resource_name),
      );
      return {
        id,
        title: optionTitle(items[0].resource_type, items[0].signal),
        signal: items[0].signal,
        resourceType: items[0].resource_type,
        affectedResources: items.length,
        recommendedCanary: items[0],
        adapter: {
          available: true,
          label:
            {
              'aws.lambda.function:logs':
                'Elastic CloudWatch log collection adapter',
              'aws.lambda.function:traces':
                'Elastic Python Lambda tracing adapter',
              'aws.ecs.service:traces':
                'Runtime-aware ECS tracing adapter',
              'aws.eks.cluster:metrics':
                'OpenTelemetry Kubernetes metrics adapter',
              'aws.rds.instance:database':
                'RDS Performance Insights adapter',
            }[id] ?? 'Dedicated visibility adapter',
        },
      };
    })
    .sort((left, right) => left.title.localeCompare(right.title));
  const selection = await readVisibilitySelection();
  return { options, ...selection };
}

async function persistVisibilitySelection(selection: {
  selectedProposalIds: string[];
  approvals: Record<string, VisibilityApproval>;
  deployedProposalIds: string[];
}): Promise<void> {
  await writeFile(
    visibilitySelectionPath,
    `${JSON.stringify(
      {
        schema_version: '1.0',
        selected_at: new Date().toISOString(),
        ...selection,
      },
      null,
      2,
    )}\n`,
    { mode: 0o600 },
  );
}

export async function saveVisibilitySelection(input: unknown): Promise<{
  options: VisibilityOption[];
  selectedProposalIds: string[];
  approvals: Record<string, VisibilityApproval>;
  deployedProposalIds: string[];
}> {
  const selectedProposalIds =
    input &&
    typeof input === 'object' &&
    Array.isArray((input as { selectedProposalIds?: unknown }).selectedProposalIds)
      ? (input as { selectedProposalIds: unknown[] }).selectedProposalIds
      : null;
  if (
    !selectedProposalIds ||
    selectedProposalIds.length > 100 ||
    !selectedProposalIds.every(
      (id) => typeof id === 'string' && /^[a-f0-9]{32}$/.test(id),
    )
  ) {
    throw new Error('Invalid visibility proposal selection');
  }
  const availableIds = new Set((await readProposals()).map((item) => item.id));
  const uniqueIds = [...new Set(selectedProposalIds as string[])];
  if (uniqueIds.some((id) => !availableIds.has(id))) {
    throw new Error('Visibility selection contains an unknown proposal');
  }
  const inputApprovals =
    input &&
    typeof input === 'object' &&
    (input as { approvals?: unknown }).approvals &&
    typeof (input as { approvals?: unknown }).approvals === 'object'
      ? ((input as { approvals: Record<string, unknown> }).approvals ?? {})
      : {};
  const approvals: Record<string, VisibilityApproval> = {};
  for (const id of uniqueIds) {
    const value = inputApprovals[id];
    const approval =
      value && typeof value === 'object' && !Array.isArray(value)
        ? (value as Partial<VisibilityApproval>)
        : {};
    approvals[id] = {
      ownerApproved: approval.ownerApproved === true,
      costReviewed: approval.costReviewed === true,
      rollbackReviewed: approval.rollbackReviewed === true,
    };
  }
  const currentSelection = await readVisibilitySelection();
  if (
    currentSelection.deployedProposalIds.some((id) => !uniqueIds.includes(id))
  ) {
    throw new Error(
      'Roll back a deployed visibility canary before removing it from scope',
    );
  }
  const deployedProposalIds = currentSelection.deployedProposalIds;
  await persistVisibilitySelection({
    selectedProposalIds: uniqueIds,
    approvals,
    deployedProposalIds,
  });
  return visibilityExpansionStatus();
}

const approvalComplete = (approval?: VisibilityApproval): boolean =>
  Boolean(
    approval?.ownerApproved &&
      approval.costReviewed &&
      approval.rollbackReviewed,
  );

const lambdaLogSource = (proposal: VisibilityProposal) => ({
  kind: 'cloudwatch',
  region: proposal.resource_arn.split(':')[3],
  log_group_name: `/aws/lambda/${proposal.resource_name}`,
  policy_template: 'lambda',
  input_type: 'aws-cloudwatch',
  dataset: 'aws.lambda_logs',
});

async function runLambdaLogAdapter(
  action: 'deploy' | 'rollback',
  proposal: VisibilityProposal,
  write: LogWriter,
): Promise<void> {
  const [kibanaUrl, username, password, agentPolicyId] = await Promise.all([
    readPrivateTerraformOutput('kibana_url'),
    readPrivateTerraformOutput('username'),
    readPrivateTerraformOutput('password'),
    readPrivateTerraformOutput('agent_policy_id'),
  ]);
  const result = await executeCommand(
    'python3',
    [
      path.join(
        repoRoot,
        'examples/aws/scripts/sync_existing_log_integrations.py',
      ),
      action === 'deploy' ? 'sync-selected' : 'cleanup-selected',
    ],
    {
      cwd: repoRoot,
      write,
      env: {
        ...process.env,
        AGENT_POLICY_ID: agentPolicyId,
        KIBANA_PASSWORD: password,
        KIBANA_URL: kibanaUrl,
        KIBANA_USERNAME: username,
        POLICY_PREFIX: 'aws-poc-canary-',
        SOURCES_JSON: JSON.stringify([lambdaLogSource(proposal)]),
      },
    },
  );
  if (result.exitCode !== 0) {
    throw Object.assign(new Error(`Lambda log adapter ${action} failed`), {
      exitCode: result.exitCode,
    });
  }
}

async function runWorkloadAdapter(
  action: 'deploy' | 'rollback',
  proposal: VisibilityProposal,
  write: LogWriter,
): Promise<void> {
  const [kibanaUrl, username, password] = await Promise.all([
    readPrivateTerraformOutput('kibana_url'),
    readPrivateTerraformOutput('username'),
    readPrivateTerraformOutput('password'),
  ]);
  let elasticsearchUrl: string;
  try {
    elasticsearchUrl = await readPrivateTerraformOutput('elasticsearch_url');
  } catch {
    elasticsearchUrl = kibanaUrl.replace('.kb.', '.es.');
    if (elasticsearchUrl === kibanaUrl) {
      throw new Error(
        'Unable to determine the Elasticsearch endpoint for this deployment',
      );
    }
  }
  const result = await executeCommand(
    'python3',
    [
      path.join(toolDirectory, 'python/visibility_adapters.py'),
      action,
      '--proposal-json',
      JSON.stringify(proposal),
      '--state',
      visibilityAdapterStatePath,
    ],
    {
      cwd: repoRoot,
      write,
      env: {
        ...process.env,
        ELASTICSEARCH_PASSWORD: password,
        ELASTICSEARCH_URL: elasticsearchUrl,
        ELASTICSEARCH_USERNAME: username,
      },
    },
  );
  if (result.exitCode !== 0) {
    throw Object.assign(
      new Error(`${optionTitle(proposal.resource_type, proposal.signal)} failed`),
      { exitCode: result.exitCode },
    );
  }
}

async function runVisibilityAdapter(
  action: 'deploy' | 'rollback',
  proposal: VisibilityProposal,
  write: LogWriter,
): Promise<void> {
  if (
    proposal.resource_type === 'aws.lambda.function' &&
    proposal.signal === 'logs'
  ) {
    await runLambdaLogAdapter(action, proposal, write);
  } else {
    await runWorkloadAdapter(action, proposal, write);
  }
}

export async function deployVisibilityExpansions(
  write: LogWriter,
): Promise<unknown> {
  const selection = await readVisibilitySelection();
  const proposals = await readProposals();
  const byId = new Map(proposals.map((proposal) => [proposal.id, proposal]));
  const deployable = selection.selectedProposalIds
    .filter((id) => !selection.deployedProposalIds.includes(id))
    .map((id) => byId.get(id))
    .filter(
      (proposal): proposal is VisibilityProposal =>
        Boolean(proposal && approvalComplete(selection.approvals[proposal.id])),
    );
  if (!deployable.length) {
    throw new Error(
      'No approved, adapter-ready visibility canaries are waiting for deployment',
    );
  }
  write(`Deploying ${deployable.length} approved visibility canary adapters`);
  for (const proposal of deployable) {
    write(`Deploying ${optionTitle(proposal.resource_type, proposal.signal)}`);
    await runVisibilityAdapter('deploy', proposal, write);
    selection.deployedProposalIds = [
      ...new Set([...selection.deployedProposalIds, proposal.id]),
    ];
    await persistVisibilitySelection(selection);
    write(`${proposal.resource_name}: adapter deployed`);
  }
  return visibilityExpansionStatus();
}

export async function rollbackVisibilityExpansions(
  write: LogWriter,
): Promise<unknown> {
  const selection = await readVisibilitySelection();
  const proposals = await readProposals();
  const byId = new Map(proposals.map((proposal) => [proposal.id, proposal]));
  const deployed = selection.deployedProposalIds
    .map((id) => byId.get(id))
    .filter((proposal): proposal is VisibilityProposal => Boolean(proposal));
  if (!deployed.length) {
    throw new Error('No deployed visibility canaries are available to roll back');
  }
  write(`Rolling back ${deployed.length} visibility canary adapters`);
  for (const proposal of [...deployed].reverse()) {
    write(`Rolling back ${optionTitle(proposal.resource_type, proposal.signal)}`);
    await runVisibilityAdapter('rollback', proposal, write);
    selection.deployedProposalIds = selection.deployedProposalIds.filter(
      (id) => id !== proposal.id,
    );
    await persistVisibilitySelection(selection);
    write(`${proposal.resource_name}: rollback complete`);
  }
  return visibilityExpansionStatus();
}

export async function runBrownfieldDiscovery(write: LogWriter): Promise<unknown> {
  const { config } = await readDeploymentConfig();
  if ((await readVisibilitySelection()).deployedProposalIds.length) {
    throw new Error(
      'Roll back deployed visibility canaries before running discovery again',
    );
  }
  if (await exists(analysisPath)) await unlink(analysisPath);
  if (await exists(visibilitySelectionPath)) await unlink(visibilitySelectionPath);
  write('Starting read-only AWS control-plane discovery');
  write('No resources, logging settings, or workloads will be changed');
  const result = await executeCommand(
    'python3',
    [
      path.join(toolDirectory, 'python/aws_brownfield_discovery.py'),
      '--output',
      manifestPath,
      '--bootstrap-region',
      config.aws_region,
      '--max-api-calls',
      '2000',
      '--max-resources-per-type',
      '500',
      '--parallel-regions',
      '4',
    ],
    { cwd: repoRoot, write },
  );
  if (result.exitCode !== 0) {
    throw Object.assign(new Error('AWS brownfield discovery failed'), {
      exitCode: result.exitCode,
    });
  }
  return summary(manifestPath);
}

export async function runBrownfieldAnalysis(write: LogWriter): Promise<unknown> {
  if (!(await exists(manifestPath))) {
    throw new Error('Run AWS environment discovery before analysis');
  }
  if ((await readVisibilitySelection()).deployedProposalIds.length) {
    throw new Error(
      'Roll back deployed visibility canaries before running analysis again',
    );
  }
  if (await exists(visibilitySelectionPath)) await unlink(visibilitySelectionPath);
  write('Analyzing the local manifest without changing AWS or Elastic');
  const result = await executeCommand(
    'python3',
    [
      path.join(toolDirectory, 'python/analyze_brownfield.py'),
      '--manifest',
      manifestPath,
      '--output',
      analysisPath,
    ],
    { cwd: repoRoot, write },
  );
  if (result.exitCode !== 0) {
    throw Object.assign(new Error('Brownfield analysis failed'), {
      exitCode: result.exitCode,
    });
  }
  return summary(analysisPath);
}

export async function readBrownfieldArtifact(
  artifact: 'manifest' | 'analysis',
): Promise<string> {
  const filePath = artifact === 'manifest' ? manifestPath : analysisPath;
  if (!(await exists(filePath))) throw new Error(`${artifact} is not available`);
  return readFile(filePath, 'utf8');
}
