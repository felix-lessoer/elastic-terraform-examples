import { execa } from 'execa';
import { gcpServiceIds } from './gcp-integrations.js';

export type CommandId =
  | 'gcp.identity'
  | 'gcp.discover'
  | 'gcloud.version'
  | 'terraform.version'
  | 'terraform.init'
  | 'terraform.plan'
  | 'terraform.apply'
  | 'terraform.show';

export interface CommandResult {
  exitCode: number;
  stdout: string;
  stderr: string;
}

export interface CommandRunner {
  run(
    id: CommandId,
    values: Record<string, string>,
    options: { cwd: string; write(line: string): void },
  ): Promise<CommandResult>;
}

const identifier = /^[a-z][a-z0-9-]{4,61}[a-z0-9]$/;
const planName = /^\.cloud-poc-[a-z-]+\.tfplan$/;
const manifestPath = /^\/[A-Za-z0-9_./-]+\/gcp-manifest\.json$/;
const labelKey = /^[a-z][a-z0-9_-]{0,62}$/;
const labelValue = /^[a-z0-9_-]{1,63}$/;
const billingDatasetId = /^[A-Za-z0-9_.:-]{0,256}$/;

function required(
  values: Record<string, string>,
  key: string,
  pattern: RegExp,
): string {
  const value = values[key] ?? '';
  if (!pattern.test(value)) throw new Error(`Invalid command value: ${key}`);
  return value;
}

function encodedLabels(values: Record<string, string>): string {
  let parsed: unknown;
  try {
    parsed = JSON.parse(values.companyLabels ?? '');
  } catch {
    throw new Error('Invalid command value: companyLabels');
  }
  if (
    !parsed ||
    Array.isArray(parsed) ||
    typeof parsed !== 'object' ||
    Object.entries(parsed).some(
      ([key, value]) =>
        !labelKey.test(key) ||
        typeof value !== 'string' ||
        !labelValue.test(value),
    )
  ) {
    throw new Error('Invalid command value: companyLabels');
  }
  return JSON.stringify(parsed);
}

function encodedRequiredLabelKeys(
  values: Record<string, string>,
): string {
  let parsed: unknown;
  try {
    parsed = JSON.parse(values.requiredLabelKeys ?? '');
  } catch {
    throw new Error('Invalid command value: requiredLabelKeys');
  }
  if (
    !Array.isArray(parsed) ||
    parsed.some((key) => typeof key !== 'string' || !labelKey.test(key))
  ) {
    throw new Error('Invalid command value: requiredLabelKeys');
  }
  return JSON.stringify(parsed);
}

function requiredBoolean(
  values: Record<string, string>,
  key: string,
): string {
  const value = values[key];
  if (value !== 'true' && value !== 'false') {
    throw new Error(`Invalid command value: ${key}`);
  }
  return value;
}

function selectedServices(values: Record<string, string>): Set<string> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(values.selectedServiceIds ?? '');
  } catch {
    throw new Error('Invalid command value: selectedServiceIds');
  }
  if (
    !Array.isArray(parsed) ||
    parsed.some(
      (service) =>
        typeof service !== 'string' ||
        !gcpServiceIds.includes(service as (typeof gcpServiceIds)[number]),
    )
  ) {
    throw new Error('Invalid command value: selectedServiceIds');
  }
  return new Set(parsed);
}

const commands: Record<
  CommandId,
  {
    executable: 'gcloud' | 'terraform' | 'python3';
    timeoutMs: number;
    args(values: Record<string, string>): string[];
  }
> = {
  'gcloud.version': {
    executable: 'gcloud',
    timeoutMs: 30_000,
    args: () => ['version', '--format=json'],
  },
  'gcp.identity': {
    executable: 'gcloud',
    timeoutMs: 30_000,
    args: (values) => [
      'projects',
      'describe',
      required(values, 'projectId', identifier),
      '--format=json(projectId,projectNumber,name,lifecycleState)',
    ],
  },
  'terraform.version': {
    executable: 'terraform',
    timeoutMs: 30_000,
    args: () => ['version', '-json'],
  },
  'gcp.discover': {
    executable: 'python3',
    timeoutMs: 300_000,
    args: (values) => [
      'scripts/gcp_brownfield_discovery.py',
      '--project',
      required(values, 'projectId', identifier),
      '--output',
      required(values, 'manifestPath', manifestPath),
      '--max-api-calls',
      '100',
      '--max-resources',
      '5000',
      '--max-concurrency',
      '4',
      '--per-call-timeout',
      '15',
    ],
  },
  'terraform.init': {
    executable: 'terraform',
    timeoutMs: 300_000,
    args: () => ['init', '-input=false', '-no-color'],
  },
  'terraform.plan': {
    executable: 'terraform',
    timeoutMs: 900_000,
    args: (values) => {
      const projectId = required(values, 'projectId', identifier);
      const selected = selectedServices(values);
      return [
        'plan',
        '-input=false',
        '-no-color',
        `-out=${required(values, 'plan', planName)}`,
        `-var=google_cloud_project=${projectId}`,
        `-var=company_labels=${encodedLabels(values)}`,
        `-var=required_label_keys=${encodedRequiredLabelKeys(values)}`,
        `-var=elastic_labels_required=${requiredBoolean(
          values,
          'elasticLabelsRequired',
        )}`,
        `-var=gcp_discovery_manifest_path=${required(
          values,
          'manifestPath',
          manifestPath,
        )}`,
        `-var=enable_gke_metrics=${selected.has('gke')}`,
        `-var=enable_cloudrun_metrics=${selected.has('cloudrun')}`,
        `-var=enable_cloudsql_metrics=${selected.has('cloudsql')}`,
        `-var=enable_pubsub_metrics=${selected.has('pubsub')}`,
        `-var=enable_firestore_metrics=${selected.has('firestore')}`,
        `-var=enable_dataproc_metrics=${selected.has('dataproc')}`,
        `-var=enable_redis_metrics=${selected.has('redis')}`,
        `-var=enable_billing_metrics=${selected.has('billing')}`,
        `-var=billing_dataset_id=${required(
          values,
          'billingDatasetId',
          billingDatasetId,
        )}`,
      ];
    },
  },
  'terraform.apply': {
    executable: 'terraform',
    timeoutMs: 1_800_000,
    args: (values) => [
      'apply',
      '-input=false',
      '-no-color',
      required(values, 'plan', planName),
    ],
  },
  'terraform.show': {
    executable: 'terraform',
    timeoutMs: 120_000,
    args: (values) => [
      'show',
      '-json',
      required(values, 'plan', planName),
    ],
  },
};

export function commandArguments(
  id: CommandId,
  values: Record<string, string>,
): string[] {
  return commands[id].args(values);
}

const secretKeys = [
  'EC_API_KEY',
  'GOOGLE_APPLICATION_CREDENTIALS',
  'GOOGLE_OAUTH_ACCESS_TOKEN',
  'ELASTICSEARCH_PASSWORD',
] as const;

export function redact(
  value: string,
  environment: NodeJS.ProcessEnv = process.env,
): string {
  let output = value;
  for (const key of secretKeys) {
    const secret = environment[key];
    if (secret && secret.length >= 6) {
      output = output.split(secret).join('[REDACTED]');
    }
  }
  return output
    .replace(/(Authorization:\s*(?:ApiKey|Basic|Bearer)\s+)\S+/gi, '$1[REDACTED]')
    .replace(
      /("(?:password|api_?key|secret|token)"\s*:\s*")[^"]+(")/gi,
      '$1[REDACTED]$2',
    );
}

export class FixedCommandRunner implements CommandRunner {
  async run(
    id: CommandId,
    values: Record<string, string>,
    options: { cwd: string; write(line: string): void },
  ): Promise<CommandResult> {
    const definition = commands[id];
    if (!definition) throw new Error('Command is not allow-listed');
    const args = commandArguments(id, values);
    options.write(redact(`$ ${definition.executable} ${args.join(' ')}`));
    const child = execa(definition.executable, args, {
      cwd: options.cwd,
      reject: false,
      stdin: 'ignore',
      timeout: definition.timeoutMs,
    });
    child.stdout?.on('data', (chunk) =>
      options.write(redact(String(chunk))),
    );
    child.stderr?.on('data', (chunk) =>
      options.write(redact(String(chunk))),
    );
    let result;
    try {
      result = await child;
    } catch (error) {
      const code =
        error && typeof error === 'object' && 'code' in error
          ? String(error.code)
          : '';
      if (code === 'ENOENT') {
        return {
          exitCode: 127,
          stdout: '',
          stderr:
            `Required command "${definition.executable}" is not installed or is not on PATH. ` +
            `Install it, restart the PoC Builder, and run Preflight again.`,
        };
      }
      throw error;
    }
    if (result.code === 'ENOENT') {
      return {
        exitCode: 127,
        stdout: '',
        stderr:
          `Required command "${definition.executable}" is not installed or is not on PATH. ` +
          `Install it, restart the PoC Builder, and run Preflight again.`,
      };
    }
    return {
      exitCode: result.exitCode ?? 1,
      stdout: redact(result.stdout),
      stderr: redact(result.stderr || result.shortMessage || ''),
    };
  }
}
