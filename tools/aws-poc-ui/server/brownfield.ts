import { constants } from 'node:fs';
import { access, readFile, stat, unlink, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { readDeploymentConfig, repoRoot } from './config.js';
import { executeCommand, type LogWriter } from './run-manager.js';

const toolDirectory = path.join(repoRoot, 'tools/aws-poc-ui');
const dataDirectory = path.join(toolDirectory, '.elastic-poc');
const manifestPath = path.join(dataDirectory, 'manifest.json');
const analysisPath = path.join(dataDirectory, 'analysis.json');
const visibilitySelectionPath = path.join(
  dataDirectory,
  'visibility-selection.json',
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

async function readSelectedProposalIds(): Promise<string[]> {
  if (!(await exists(visibilitySelectionPath))) return [];
  const parsed = JSON.parse(await readFile(visibilitySelectionPath, 'utf8')) as {
    selectedProposalIds?: unknown;
  };
  return Array.isArray(parsed.selectedProposalIds)
    ? parsed.selectedProposalIds.filter(
        (id): id is string => typeof id === 'string',
      )
    : [];
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
      };
    })
    .sort((left, right) => left.title.localeCompare(right.title));
  return { options, selectedProposalIds: await readSelectedProposalIds() };
}

export async function saveVisibilitySelection(input: unknown): Promise<{
  options: VisibilityOption[];
  selectedProposalIds: string[];
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
  await writeFile(
    visibilitySelectionPath,
    `${JSON.stringify(
      {
        schema_version: '1.0',
        selected_at: new Date().toISOString(),
        selectedProposalIds: uniqueIds,
      },
      null,
      2,
    )}\n`,
    { mode: 0o600 },
  );
  return visibilityExpansionStatus();
}

export async function runBrownfieldDiscovery(write: LogWriter): Promise<unknown> {
  const { config } = await readDeploymentConfig();
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
