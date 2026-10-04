import { execa } from 'execa';

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

function required(
  values: Record<string, string>,
  key: string,
  pattern: RegExp,
): string {
  const value = values[key] ?? '';
  if (!pattern.test(value)) throw new Error(`Invalid command value: ${key}`);
  return value;
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
    args: (values) => [
      'plan',
      '-input=false',
      '-no-color',
      `-out=${required(values, 'plan', planName)}`,
    ],
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
    const args = definition.args(values);
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
    return {
      exitCode: result.exitCode ?? 1,
      stdout: redact(result.stdout),
      stderr: redact(result.stderr || result.shortMessage || ''),
    };
  }
}
