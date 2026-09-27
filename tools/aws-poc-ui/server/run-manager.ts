import { EventEmitter } from 'node:events';
import { randomUUID } from 'node:crypto';
import { execa } from 'execa';

export type RunStatus = 'running' | 'succeeded' | 'failed';

export interface RunRecord {
  id: string;
  step: string;
  title: string;
  status: RunStatus;
  startedAt: string;
  finishedAt?: string;
  exitCode?: number;
  logs: string[];
  result?: unknown;
}

export type LogWriter = (line: string) => void;
export type RunTask = (write: LogWriter) => Promise<unknown>;

const MAX_LOG_LINES = 2_000;

function redact(input: string): string {
  let output = input;
  for (const key of [
    'EC_API_KEY',
    'AWS_SECRET_ACCESS_KEY',
    'AWS_SESSION_TOKEN',
  ]) {
    const value = process.env[key];
    if (value && value.length >= 6) {
      output = output.split(value).join('[REDACTED]');
    }
  }
  return output
    .replace(/(Authorization:\s*(?:ApiKey|Basic|Bearer)\s+)\S+/gi, '$1[REDACTED]')
    .replace(
      /("(?:password|api_?key|secret|token)"\s*:\s*")[^"]+(")/gi,
      '$1[REDACTED]$2',
    );
}

export async function executeCommand(
  command: string,
  args: string[],
  options: {
    cwd: string;
    write: LogWriter;
    env?: NodeJS.ProcessEnv;
  },
): Promise<{
  exitCode: number;
  stdout: string;
  stderr: string;
  failureMessage?: string;
}> {
  options.write(`$ ${command} ${args.join(' ')}`);
  const child = execa(command, args, {
    cwd: options.cwd,
    env: options.env,
    reject: false,
    stdin: 'ignore',
  });

  child.stdout?.on('data', (chunk: Buffer | string) => {
    for (const line of String(chunk).split(/\r?\n/)) {
      if (line) options.write(line);
    }
  });
  child.stderr?.on('data', (chunk: Buffer | string) => {
    for (const line of String(chunk).split(/\r?\n/)) {
      if (line) options.write(line);
    }
  });

  const result = await child;
  if (result.exitCode !== 0 && !result.stderr && result.shortMessage) {
    options.write(result.shortMessage);
  }
  return {
    exitCode: result.exitCode ?? 1,
    stdout: result.stdout,
    stderr: result.stderr,
    failureMessage: result.failed ? result.shortMessage : undefined,
  };
}

export class RunManager {
  readonly events = new EventEmitter();
  private readonly runs = new Map<string, RunRecord>();
  private activeRunId?: string;

  list(): RunRecord[] {
    return [...this.runs.values()].sort((a, b) =>
      b.startedAt.localeCompare(a.startedAt),
    );
  }

  get(id: string): RunRecord | undefined {
    return this.runs.get(id);
  }

  start(step: string, title: string, task: RunTask): RunRecord {
    if (this.activeRunId) {
      throw new Error('Another operation is already running');
    }

    const record: RunRecord = {
      id: randomUUID(),
      step,
      title,
      status: 'running',
      startedAt: new Date().toISOString(),
      logs: [],
    };
    this.runs.set(record.id, record);
    this.activeRunId = record.id;
    this.emit(record);

    const write: LogWriter = (line) => {
      record.logs.push(redact(line));
      if (record.logs.length > MAX_LOG_LINES) record.logs.shift();
      this.emit(record);
    };

    void task(write)
      .then((result) => {
        record.status = 'succeeded';
        record.exitCode = 0;
        record.result = result;
      })
      .catch((error: unknown) => {
        record.status = 'failed';
        record.exitCode =
          error instanceof Error && 'exitCode' in error
            ? Number(error.exitCode)
            : 1;
        write(error instanceof Error ? error.message : String(error));
      })
      .finally(() => {
        record.finishedAt = new Date().toISOString();
        if (this.activeRunId === record.id) this.activeRunId = undefined;
        this.emit(record);
      });

    return record;
  }

  private emit(record: RunRecord): void {
    this.events.emit(record.id, record);
    this.events.emit('all', record);
  }
}
