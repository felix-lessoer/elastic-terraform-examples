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

interface DiscoveredResource {
  arn: string;
  configuration?: Record<string, unknown>;
}

export interface VisibilityOption {
  id: string;
  title: string;
  signal: string;
  resourceType: string;
  affectedResources: number;
  recommendedCanary: VisibilityProposal;
  candidates: Array<
    VisibilityProposal & {
      adapter: {
        available: boolean;
        label: string;
      };
    }
  >;
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

async function readResourceConfigurations(): Promise<
  Map<string, Record<string, unknown>>
> {
  if (!(await exists(manifestPath))) return new Map();
  const parsed = JSON.parse(await readFile(manifestPath, 'utf8')) as {
    resources?: DiscoveredResource[];
  };
  return new Map(
    (parsed.resources ?? []).map((resource) => [
      resource.arn,
      resource.configuration ?? {},
    ]),
  );
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

function adapterFor(
  proposal: VisibilityProposal,
  resourceConfiguration: Record<string, unknown> = {},
): VisibilityOption['adapter'] {
  const id = `${proposal.resource_type}:${proposal.signal}`;
  if (
    id === 'aws.ecs.service:traces' &&
    Number(resourceConfiguration.desired_count ?? 0) < 1
  ) {
    return {
      available: false,
      label: 'Inactive ECS service — choose a canary with running tasks',
    };
  }
  if (
    id === 'aws.lambda.function:traces' &&
    !String(resourceConfiguration.runtime ?? '').startsWith('python')
  ) {
    return {
      available: false,
      label: `Unsupported Lambda runtime: ${
        resourceConfiguration.runtime ?? 'unknown'
      }`,
    };
  }
  return {
    available: true,
    label:
      {
        'aws.lambda.function:logs':
          'Elastic CloudWatch log collection adapter',
        'aws.lambda.function:traces':
          'Elastic Python Lambda tracing adapter',
        'aws.ecs.service:traces': 'Runtime-aware ECS tracing adapter',
        'aws.eks.cluster:metrics':
          'OpenTelemetry metrics adapter with temporary EKS setup access',
        'aws.rds.instance:database': 'RDS Performance Insights adapter',
      }[id] ?? 'Dedicated visibility adapter',
  };
}

export async function visibilityExpansionStatus(): Promise<{
  options: VisibilityOption[];
  selectedProposalIds: string[];
  approvals: Record<string, VisibilityApproval>;
  deployedProposalIds: string[];
}> {
  const [proposals, resourceConfigurations] = await Promise.all([
    readProposals(),
    readResourceConfigurations(),
  ]);
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
        candidates: items.map((proposal) => ({
          ...proposal,
          adapter: adapterFor(
            proposal,
            resourceConfigurations.get(proposal.resource_arn),
          ),
        })),
        adapter: adapterFor(
          items[0],
          resourceConfigurations.get(items[0].resource_arn),
        ),
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
    selectedProposalIds.length > 1_000 ||
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
  const approvals: Record<string, VisibilityApproval> = {};
  for (const id of uniqueIds) {
    approvals[id] = {
      ownerApproved: true,
      costReviewed: true,
      rollbackReviewed: true,
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

const lambdaLogSource = (proposal: VisibilityProposal) => ({
  kind: 'cloudwatch',
  region: proposal.resource_arn.split(':')[3],
  log_group_name: `/aws/lambda/${proposal.resource_name}`,
  policy_template: 'lambda',
  input_type: 'aws-cloudwatch',
  dataset: 'aws.lambda_logs',
});

async function runLambdaLogAdapters(
  action: 'deploy' | 'rollback',
  proposals: VisibilityProposal[],
  write: LogWriter,
): Promise<void> {
  if (!proposals.length) return;
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
      action === 'deploy' ? 'sync' : 'cleanup-selected',
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
        SOURCES_JSON: JSON.stringify(proposals.map(lambdaLogSource)),
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
  const resourceConfigurations = await readResourceConfigurations();
  const resourceConfiguration =
    resourceConfigurations.get(proposal.resource_arn) ?? {};
  const isDocumentDb =
    proposal.resource_type === 'aws.rds.instance' &&
    proposal.signal === 'database' &&
    resourceConfiguration.engine === 'docdb';
  if (isDocumentDb && action === 'rollback') {
    await runDocumentDbMetricAdapter('cleanup-selected', proposal, write);
  }
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
  if (isDocumentDb && action === 'deploy') {
    await runDocumentDbMetricAdapter('sync', proposal, write);
  }
}

export function documentDbMetricSpec(proposal: VisibilityProposal) {
  const region = proposal.resource_arn.split(':')[3];
  return {
    name: 'aws-managed-docdb-canary',
    description: `Elastic PoC metrics for DocumentDB ${proposal.resource_name}`,
    policy_template: 'cloudwatch',
    default_region: region,
    connector_name: 'elastic-observability-docdb-canary',
    inputs: {
      'cloudwatch-aws/metrics': {
        enabled: true,
        streams: {
          'aws.cloudwatch_metrics': {
            enabled: true,
            vars: JSON.stringify({
              period: '5m',
              latency: '5m',
              regions: [region],
              include_linked_accounts: false,
              metrics: [
                '- namespace: AWS/DocDB',
                '  resource_type: rds:db',
                '  name:',
                '    - CPUUtilization',
                '    - DatabaseConnections',
                '    - FreeableMemory',
                '    - FreeLocalStorage',
                '    - ReadLatency',
                '    - WriteLatency',
                '    - ReadThroughput',
                '    - WriteThroughput',
                '  statistic:',
                '    - Average',
                '    - Maximum',
              ].join('\n'),
            }),
          },
        },
      },
    },
  };
}

async function runDocumentDbMetricAdapter(
  action: 'sync' | 'cleanup-selected',
  proposal: VisibilityProposal,
  write: LogWriter,
): Promise<void> {
  write(
    action === 'sync'
      ? 'Configuring Elastic collection for the AWS/DocDB CloudWatch namespace'
      : 'Removing the canary AWS/DocDB metric collector',
  );
  const [kibanaUrl, username, password, roleArn] = await Promise.all([
    readPrivateTerraformOutput('kibana_url'),
    readPrivateTerraformOutput('username'),
    readPrivateTerraformOutput('password'),
    readPrivateTerraformOutput('aws_managed_collector_role_arn'),
  ]);
  const result = await executeCommand(
    'python3',
    [
      path.join(
        repoRoot,
        'examples/aws/scripts/sync_managed_metric_integrations.py',
      ),
      action,
    ],
    {
      cwd: repoRoot,
      write,
      env: {
        ...process.env,
        AWS_ROLE_ARN: roleArn,
        KIBANA_PASSWORD: password,
        KIBANA_URL: kibanaUrl,
        KIBANA_USERNAME: username,
        SPECS_JSON: JSON.stringify([documentDbMetricSpec(proposal)]),
        UPDATE_EXISTING: 'true',
      },
    },
  );
  if (result.exitCode !== 0) {
    throw Object.assign(new Error('DocumentDB metric collector setup failed'), {
      exitCode: result.exitCode,
    });
  }
}

async function runVisibilityAdapter(
  action: 'deploy' | 'rollback',
  proposal: VisibilityProposal,
  write: LogWriter,
): Promise<void> {
  await runWorkloadAdapter(action, proposal, write);
}

export async function deployVisibilityExpansions(
  write: LogWriter,
): Promise<unknown> {
  const selection = await readVisibilitySelection();
  const proposals = await readProposals();
  const resourceConfigurations = await readResourceConfigurations();
  const byId = new Map(proposals.map((proposal) => [proposal.id, proposal]));
  const approved = selection.selectedProposalIds
    .filter((id) => !selection.deployedProposalIds.includes(id))
    .map((id) => byId.get(id))
    .filter((proposal): proposal is VisibilityProposal => Boolean(proposal));
  const deployable = approved.filter(
    (proposal) =>
      adapterFor(
        proposal,
        resourceConfigurations.get(proposal.resource_arn),
      ).available,
  );
  const blocked = approved.filter(
    (proposal) =>
      !adapterFor(
        proposal,
        resourceConfigurations.get(proposal.resource_arn),
      ).available,
    );
  if (!deployable.length) {
    throw new Error(
      'No selected, adapter-ready visibility canaries are waiting for deployment',
    );
  }
  for (const proposal of blocked) {
    write(
      `Skipping ${proposal.resource_name}: ${
        adapterFor(
          proposal,
          resourceConfigurations.get(proposal.resource_arn),
        ).label
      }`,
    );
  }
  write(`Deploying ${deployable.length} selected visibility canary adapters`);
  const failures: string[] = [];
  const lambdaLogs = deployable.filter(
    (proposal) =>
      proposal.resource_type === 'aws.lambda.function' &&
      proposal.signal === 'logs',
  );
  const workloadAdapters = deployable.filter(
    (proposal) => !lambdaLogs.includes(proposal),
  );
  if (lambdaLogs.length) {
    write(
      `Deploying Lambda log collection for ${lambdaLogs.length} selected functions`,
    );
    try {
      const alreadyDeployedLambdaLogs = selection.deployedProposalIds
        .map((id) => byId.get(id))
        .filter(
          (proposal): proposal is VisibilityProposal =>
            proposal?.resource_type === 'aws.lambda.function' &&
            proposal.signal === 'logs',
        );
      await runLambdaLogAdapters(
        'deploy',
        [...alreadyDeployedLambdaLogs, ...lambdaLogs],
        write,
      );
      selection.deployedProposalIds = [
        ...new Set([
          ...selection.deployedProposalIds,
          ...lambdaLogs.map((proposal) => proposal.id),
        ]),
      ];
      await persistVisibilitySelection(selection);
      write(`${lambdaLogs.length} Lambda log adapters deployed`);
    } catch (error) {
      failures.push(...lambdaLogs.map((proposal) => proposal.resource_name));
      write('Lambda log collector deployment needs attention');
      write(error instanceof Error ? error.message : String(error));
    }
  }
  for (const proposal of workloadAdapters) {
    write(`Deploying ${optionTitle(proposal.resource_type, proposal.signal)}`);
    try {
      await runVisibilityAdapter('deploy', proposal, write);
      selection.deployedProposalIds = [
        ...new Set([...selection.deployedProposalIds, proposal.id]),
      ];
      await persistVisibilitySelection(selection);
      write(`${proposal.resource_name}: adapter deployed`);
    } catch (error) {
      failures.push(proposal.resource_name);
      write(
        `${proposal.resource_name}: deployment needs attention; continuing with the remaining canaries`,
      );
      write(error instanceof Error ? error.message : String(error));
    }
  }
  if (failures.length) {
    throw new Error(
      `${failures.length} visibility ${
        failures.length === 1 ? 'adapter needs' : 'adapters need'
      } attention: ${failures.join(', ')}`,
    );
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
  const lambdaLogs = deployed.filter(
    (proposal) =>
      proposal.resource_type === 'aws.lambda.function' &&
      proposal.signal === 'logs',
  );
  const workloadAdapters = deployed.filter(
    (proposal) => !lambdaLogs.includes(proposal),
  );
  for (const proposal of [...workloadAdapters].reverse()) {
    write(`Rolling back ${optionTitle(proposal.resource_type, proposal.signal)}`);
    await runVisibilityAdapter('rollback', proposal, write);
    selection.deployedProposalIds = selection.deployedProposalIds.filter(
      (id) => id !== proposal.id,
    );
    await persistVisibilitySelection(selection);
    write(`${proposal.resource_name}: rollback complete`);
  }
  if (lambdaLogs.length) {
    write(`Removing Lambda log collection for ${lambdaLogs.length} functions`);
    await runLambdaLogAdapters('rollback', lambdaLogs, write);
    const lambdaIds = new Set(lambdaLogs.map((proposal) => proposal.id));
    selection.deployedProposalIds = selection.deployedProposalIds.filter(
      (id) => !lambdaIds.has(id),
    );
    await persistVisibilitySelection(selection);
    write('Lambda log collector rollback complete');
  }
  return visibilityExpansionStatus();
}

export async function reconcileDeployedVisibilityExpansions(
  write: LogWriter,
): Promise<void> {
  const selection = await readVisibilitySelection();
  const proposals = await readProposals();
  const resourceConfigurations = await readResourceConfigurations();
  const byId = new Map(proposals.map((proposal) => [proposal.id, proposal]));
  const deployedLambdaLogs = selection.deployedProposalIds
    .map((id) => byId.get(id))
    .filter(
      (proposal): proposal is VisibilityProposal =>
        proposal?.resource_type === 'aws.lambda.function' &&
        proposal.signal === 'logs',
    );
  if (deployedLambdaLogs.length) {
    try {
      await runLambdaLogAdapters('deploy', deployedLambdaLogs, write);
    } catch (error) {
      write('Lambda log collector reconciliation needs attention');
      write(error instanceof Error ? error.message : String(error));
    }
  }
  for (const id of selection.deployedProposalIds) {
    const proposal = byId.get(id);
    if (!proposal) continue;
    if (
      proposal.resource_type === 'aws.rds.instance' &&
      proposal.signal === 'database' &&
      resourceConfigurations.get(proposal.resource_arn)?.engine === 'docdb'
    ) {
      try {
        await runDocumentDbMetricAdapter('sync', proposal, write);
      } catch (error) {
        write(
          `${proposal.resource_name}: DocumentDB collector reconciliation needs attention`,
        );
        write(error instanceof Error ? error.message : String(error));
      }
    }
    if (
      proposal.resource_type === 'aws.lambda.function' &&
      proposal.signal === 'traces'
    ) {
      write(
        `${proposal.resource_name}: Lambda tracing is installed; telemetry appears after the function receives normal traffic`,
      );
    }
  }
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
