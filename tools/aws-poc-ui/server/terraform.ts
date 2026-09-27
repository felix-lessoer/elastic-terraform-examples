import { constants } from 'node:fs';
import { access, unlink } from 'node:fs/promises';
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

export type PlanAction = 'create' | 'update' | 'replace' | 'delete' | 'read';

export interface PlannedResource {
  address: string;
  module: string;
  type: string;
  name: string;
  action: PlanAction;
}

export interface PlanSummary {
  generatedAt?: string;
  resources: PlannedResource[];
  counts: Record<PlanAction, number>;
}

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

export function summarizeTerraformPlan(input: unknown): PlanSummary {
  const plan = input as {
    timestamp?: unknown;
    resource_changes?: unknown;
  };
  const counts: Record<PlanAction, number> = {
    create: 0,
    update: 0,
    replace: 0,
    delete: 0,
    read: 0,
  };
  const changes = Array.isArray(plan.resource_changes)
    ? plan.resource_changes
    : [];
  const resources = changes.flatMap((entry): PlannedResource[] => {
    if (!entry || typeof entry !== 'object') return [];
    const change = entry as {
      address?: unknown;
      module_address?: unknown;
      mode?: unknown;
      type?: unknown;
      name?: unknown;
      change?: { actions?: unknown };
    };
    if (change.mode !== 'managed' || !Array.isArray(change.change?.actions)) {
      return [];
    }
    const actions = change.change.actions.filter(
      (action): action is string => typeof action === 'string',
    );
    let action: PlanAction | undefined;
    if (actions.includes('create') && actions.includes('delete')) {
      action = 'replace';
    } else if (actions.includes('create')) {
      action = 'create';
    } else if (actions.includes('update')) {
      action = 'update';
    } else if (actions.includes('delete')) {
      action = 'delete';
    } else if (actions.includes('read')) {
      action = 'read';
    }
    if (
      !action ||
      typeof change.address !== 'string' ||
      typeof change.type !== 'string' ||
      typeof change.name !== 'string'
    ) {
      return [];
    }
    counts[action] += 1;
    return [
      {
        address: change.address,
        module:
          typeof change.module_address === 'string'
            ? change.module_address
            : 'root',
        type: change.type,
        name: change.name,
        action,
      },
    ];
  });
  resources.sort(
    (left, right) =>
      left.action.localeCompare(right.action) ||
      left.address.localeCompare(right.address),
  );
  return {
    generatedAt:
      typeof plan.timestamp === 'string' ? plan.timestamp : undefined,
    resources,
    counts,
  };
}

export async function readPlanSummary(): Promise<PlanSummary | null> {
  if (!(await exists(planFile))) return null;
  const result = await capture('terraform', [
    'show',
    '-json',
    path.basename(planFile),
  ]);
  if (result.exitCode !== 0) {
    throw new Error(result.stderr || 'Unable to read the saved Terraform plan');
  }
  return summarizeTerraformPlan(JSON.parse(result.stdout));
}

export interface PreflightCheck {
  id: string;
  label: string;
  status: 'passed' | 'failed' | 'warning';
  detail: string;
}

export function explainPreflightFailure(
  id: string,
  label: string,
  output: string,
  exitCode: number,
): string {
  if (/\bENOENT\b|not found|not recognized/i.test(output)) {
    const executable = id === 'aws' ? 'AWS CLI' : label;
    return `${executable} is not installed or is not visible to the UI. Install it, ensure its executable is on PATH, then restart the Deployment Creator.`;
  }
  if (id === 'aws') {
    if (/Unable to locate credentials|could not be found/i.test(output)) {
      return 'No AWS credentials were found. Save an AWS profile or access keys in step 1, then run preflight again.';
    }
    if (/ExpiredToken|token has expired/i.test(output)) {
      return 'The AWS session token has expired. Save fresh temporary credentials in step 1, then run preflight again.';
    }
    if (
      /InvalidClientTokenId|SignatureDoesNotMatch|UnrecognizedClientException/i.test(
        output,
      )
    ) {
      return 'AWS rejected the saved credentials. Check the access key, secret key, session token, or selected profile in step 1.';
    }
    if (/AccessDenied|not authorized/i.test(output)) {
      return 'AWS credentials were found, but the caller identity request was denied. Verify the selected account and IAM permissions.';
    }
    if (
      /Could not connect to the endpoint|ENETUNREACH|ETIMEDOUT|EAI_AGAIN/i.test(
        output,
      )
    ) {
      return 'The AWS API could not be reached. Check network access, proxy settings, and the selected AWS region.';
    }
  }
  const summary = output
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find(Boolean);
  return summary
    ? `${label} check failed: ${summary}`
    : `${label} check exited with code ${exitCode}. Review the command output for details.`;
}

function explainPreflightSuccess(
  id: string,
  label: string,
  output: string,
): string {
  if (id === 'terraform') {
    try {
      const version = (JSON.parse(output) as { terraform_version?: string })
        .terraform_version;
      if (version) return `Terraform ${version} is available`;
    } catch {
      // Fall through to the first output line.
    }
  }
  if (id === 'aws') {
    try {
      const identity = JSON.parse(output) as { Arn?: string; Account?: string };
      if (identity.Arn) return `AWS caller identity verified: ${identity.Arn}`;
      if (identity.Account) {
        return `AWS caller identity verified for account ${identity.Account}`;
      }
    } catch {
      // Fall through to the first output line.
    }
  }
  return output.split(/\r?\n/).find(Boolean) || `${label} is available`;
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
            ? explainPreflightSuccess(id, label, result.stdout)
            : explainPreflightFailure(
                id,
                label,
                [result.stderr, result.failureMessage]
                  .filter(Boolean)
                  .join('\n'),
                result.exitCode,
              ),
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
      : 'Enter and save an Elastic Cloud API key in step 1, then run preflight again',
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
  if (await exists(planFile)) await unlink(planFile);
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
  await unlink(planFile);
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
