import { constants } from 'node:fs';
import { access, readFile, stat, unlink } from 'node:fs/promises';
import path from 'node:path';
import { readDeploymentConfig, repoRoot } from './config.js';
import { executeCommand, type LogWriter } from './run-manager.js';

const toolDirectory = path.join(repoRoot, 'tools/aws-poc-ui');
const dataDirectory = path.join(toolDirectory, '.elastic-poc');
const manifestPath = path.join(dataDirectory, 'manifest.json');
const analysisPath = path.join(dataDirectory, 'analysis.json');

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

export async function runBrownfieldDiscovery(write: LogWriter): Promise<unknown> {
  const { config } = await readDeploymentConfig();
  if (await exists(analysisPath)) await unlink(analysisPath);
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
