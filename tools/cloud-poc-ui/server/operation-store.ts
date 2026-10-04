import { randomUUID } from 'node:crypto';
import { EventEmitter } from 'node:events';
import type {
  GuidedOperation,
  ProgressState,
  ProgressUpdate,
  ProviderContext,
} from './cloud-provider.js';
import { readJson, writeOwnerOnly } from './local-files.js';
import { redact } from './commands.js';

export interface OperationRecord {
  id: string;
  provider: 'gcp';
  operation: GuidedOperation;
  state: ProgressState;
  stage: string;
  message: string;
  percent?: number;
  startedAt: string;
  updatedAt: string;
  finishedAt?: string;
  logs: string[];
  result?: unknown;
}

type Task = (context: ProviderContext) => Promise<unknown>;

export class OperationStore {
  readonly events = new EventEmitter();
  private records: OperationRecord[] = [];
  private loaded = false;
  private persistence: Promise<void> = Promise.resolve();

  constructor(private readonly filePath: string) {}

  async load(): Promise<void> {
    if (this.loaded) return;
    this.records = await readJson<OperationRecord[]>(this.filePath, []);
    const now = new Date().toISOString();
    for (const record of this.records) {
      if (['queued', 'running', 'validating'].includes(record.state)) {
        record.state = 'failed';
        record.stage = 'interrupted';
        record.message = 'The local server stopped before this operation completed';
        record.finishedAt = now;
        record.updatedAt = now;
      }
    }
    this.loaded = true;
    await this.persist();
  }

  list(): OperationRecord[] {
    return [...this.records].sort((a, b) => b.startedAt.localeCompare(a.startedAt));
  }

  get(id: string): OperationRecord | undefined {
    return this.records.find((record) => record.id === id);
  }

  async start(operation: GuidedOperation, task: Task): Promise<OperationRecord> {
    await this.load();
    if (this.records.some((record) =>
      ['queued', 'running', 'validating'].includes(record.state),
    )) {
      throw new Error('Another guided operation is already running');
    }
    const now = new Date().toISOString();
    const record: OperationRecord = {
      id: randomUUID(),
      provider: 'gcp',
      operation,
      state: 'queued',
      stage: 'queued',
      message: 'Waiting to start',
      startedAt: now,
      updatedAt: now,
      logs: [],
    };
    this.records.push(record);
    await this.persist();
    void this.run(record, task);
    return record;
  }

  private async run(record: OperationRecord, task: Task): Promise<void> {
    await this.update(record, {
      state: 'running',
      stage: 'starting',
      message: 'Operation started',
    });
    const context: ProviderContext = {
      write: (line) => {
        record.logs.push(redact(line).slice(0, 16_384));
        if (record.logs.length > 2_000) record.logs.shift();
        record.updatedAt = new Date().toISOString();
        void this.persist().catch(() => {
          // A terminal update will surface persistence failures to the task.
        });
        this.events.emit(record.id, record);
      },
      progress: async (progress) => {
        await this.update(record, {
          state: progress.stage === 'validating' ? 'validating' : 'running',
          ...progress,
        });
      },
    };
    try {
      record.result = await task(context);
      await this.update(record, {
        state: 'succeeded',
        stage: 'complete',
        message: 'Operation completed',
        percent: 100,
        finishedAt: new Date().toISOString(),
      });
    } catch (error) {
      context.write(error instanceof Error ? error.message : String(error));
      await this.update(record, {
        state: 'failed',
        stage: 'failed',
        message: 'Operation failed; review the redacted local log',
        finishedAt: new Date().toISOString(),
      });
    }
  }

  private async update(
    record: OperationRecord,
    update: Partial<OperationRecord> & Partial<ProgressUpdate>,
  ): Promise<void> {
    Object.assign(record, update, { updatedAt: new Date().toISOString() });
    await this.persist();
    this.events.emit(record.id, record);
  }

  private async persist(): Promise<void> {
    if (!this.loaded) return;
    const serialized = `${JSON.stringify(this.records, null, 2)}\n`;
    const write = this.persistence.catch(() => undefined).then(() =>
      writeOwnerOnly(this.filePath, serialized),
    );
    this.persistence = write.catch(() => undefined);
    await write;
  }
}
