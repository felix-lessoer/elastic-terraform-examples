import { constants } from 'node:fs';
import { access } from 'node:fs/promises';
import path from 'node:path';
import { execa } from 'execa';
import {
  generatedVariablesPath,
  readDeploymentConfig,
  terraformDirectory,
} from './config.js';
import { executeCommand, type LogWriter } from './run-manager.js';

const planFile = path.join(terraformDirectory, '.aws-poc-ui.tfplan');
const stateFile = path.join(terraformDirectory, 'terraform.tfstate');

interface TerraformOutput {
  sensitive: boolean;
  value: unknown;
}

type TerraformOutputs = Record<string, TerraformOutput>;

async function exists(filePath: string): Promise<boolean> {
  try {
    await access(filePath, constants.F_OK);
    return true;
  } catch {
    return false;
  }
}

async function capture(
  command: string,
  args: string[],
): Promise<{ exitCode: number; stdout: string; stderr: string }> {
  const result = await execa(command, args, {
    cwd: terraformDirectory,
    reject: false,
    stdin: 'ignore',
  });
  return {
    exitCode: result.exitCode ?? 1,
    stdout: result.stdout,
    stderr: result.stderr,
  };
}

export interface PreflightCheck {
  id: string;
  label: string;
  status: 'passed' | 'failed' | 'warning';
  detail: string;
}

export async function runPreflight(write: LogWriter): Promise<{
  checks: PreflightCheck[];
  passed: boolean;
}> {
  const checks: PreflightCheck[] = [];

  const commandCheck = async (
    id: string,
    label: string,
    command: string,
    args: string[],
  ) => {
    try {
      const result = await executeCommand(command, args, {
        cwd: terraformDirectory,
        write,
      });
      checks.push({
        id,
        label,
        status: result.exitCode === 0 ? 'passed' : 'failed',
        detail:
          result.exitCode === 0
            ? result.stdout.split(/\r?\n/)[0] || 'Available'
            : result.stderr || `Exited with ${result.exitCode}`,
      });
    } catch (error) {
      checks.push({
        id,
        label,
        status: 'failed',
        detail: error instanceof Error ? error.message : String(error),
      });
    }
  };

  checks.push({
    id: 'configuration',
    label: 'Deployment configuration',
    status: (await exists(generatedVariablesPath)) ? 'passed' : 'failed',
    detail: (await exists(generatedVariablesPath))
      ? path.basename(generatedVariablesPath)
      : 'Save the configuration before continuing',
  });

  checks.push({
    id: 'elastic-key',
    label: 'Elastic Cloud API key',
    status: process.env.EC_API_KEY ? 'passed' : 'failed',
    detail: process.env.EC_API_KEY
      ? 'EC_API_KEY is present in the local server environment'
      : 'Export EC_API_KEY before starting the UI',
  });

  await commandCheck('terraform', 'Terraform', 'terraform', ['version', '-json']);
  await commandCheck('python', 'Python', 'python3', ['--version']);

  const { config } = await readDeploymentConfig();
  await commandCheck('aws', 'AWS identity', 'aws', [
    'sts',
    'get-caller-identity',
    '--region',
    config.aws_region,
    '--output',
    'json',
  ]);

  const passed = checks.every((check) => check.status !== 'failed');
  write(passed ? 'Preflight passed' : 'Preflight found blocking issues');
  return { checks, passed };
}

export async function terraformInit(write: LogWriter): Promise<void> {
  const result = await executeCommand(
    'terraform',
    ['init', '-input=false', '-no-color'],
    { cwd: terraformDirectory, write },
  );
  if (result.exitCode !== 0) {
    throw Object.assign(new Error('Terraform initialization failed'), {
      exitCode: result.exitCode,
    });
  }
}

export async function terraformPlan(write: LogWriter): Promise<void> {
  const result = await executeCommand(
    'terraform',
    [
      'plan',
      '-input=false',
      '-no-color',
      `-out=${path.basename(planFile)}`,
    ],
    { cwd: terraformDirectory, write },
  );
  if (result.exitCode !== 0) {
    throw Object.assign(new Error('Terraform plan failed'), {
      exitCode: result.exitCode,
    });
  }
}

export async function terraformApply(write: LogWriter): Promise<void> {
  if (!(await exists(planFile))) {
    throw new Error('Create a Terraform plan before applying');
  }
  const result = await executeCommand(
    'terraform',
    ['apply', '-input=false', '-no-color', path.basename(planFile)],
    { cwd: terraformDirectory, write },
  );
  if (result.exitCode !== 0) {
    throw Object.assign(new Error('Terraform apply failed'), {
      exitCode: result.exitCode,
    });
  }
}

export async function readTerraformOutputs(): Promise<TerraformOutputs> {
  const result = await capture('terraform', ['output', '-json']);
  if (result.exitCode !== 0) {
    throw new Error(result.stderr || 'Unable to read Terraform outputs');
  }
  return JSON.parse(result.stdout) as TerraformOutputs;
}

export async function readSafeTerraformOutputs(): Promise<
  Record<string, unknown>
> {
  const outputs = await readTerraformOutputs();
  return sanitizeTerraformOutputs(outputs);
}

export function sanitizeTerraformOutputs(
  outputs: TerraformOutputs,
): Record<string, unknown> {
  const allowed = new Set([
    'aws_account_id',
    'cockpit_dashboard_url',
    'kibana_url',
    'managed_integration_names',
    'project_id',
    'regional_security_agent_regions',
    'workflow_ids',
  ]);
  return Object.fromEntries(
    Object.entries(outputs)
      .filter(
        ([name, output]) => allowed.has(name) && output.sensitive !== true,
      )
      .map(([name, output]) => [name, output.value]),
  );
}

export async function deploymentStatus(): Promise<{
  configured: boolean;
  initialized: boolean;
  planned: boolean;
  deployed: boolean;
  outputs: Record<string, unknown>;
}> {
  const deployed = await exists(stateFile);
  let outputs: Record<string, unknown> = {};
  if (deployed) {
    try {
      outputs = await readSafeTerraformOutputs();
    } catch {
      // A partial or remote-state deployment may not have readable outputs yet.
    }
  }
  return {
    configured: await exists(generatedVariablesPath),
    initialized: await exists(path.join(terraformDirectory, '.terraform')),
    planned: await exists(planFile),
    deployed,
    outputs,
  };
}
