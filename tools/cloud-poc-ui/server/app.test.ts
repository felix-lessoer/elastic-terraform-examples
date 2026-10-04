import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import request from 'supertest';
import { afterEach, describe, expect, it } from 'vitest';
import type {
  CloudProvider,
  GuidedOperation,
  OperationRequest,
  ProviderContext,
} from './cloud-provider.js';
import { createApp } from './app.js';
import { redact } from './commands.js';
import { saveCredentials } from './credentials.js';
import { OperationStore } from './operation-store.js';

const temporaryDirectories: string[] = [];

async function temporaryDirectory(): Promise<string> {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'cloud-poc-ui-'));
  temporaryDirectories.push(directory);
  return directory;
}

afterEach(async () => {
  await Promise.all(
    temporaryDirectories.splice(0).map((directory) =>
      fs.rm(directory, { recursive: true, force: true }),
    ),
  );
});

function fakeProvider(): CloudProvider {
  return {
    slug: 'gcp',
    displayName: 'Google Cloud',
    terraformDirectory: '/tmp',
    credentialStatus: async () => ({
      elasticConfigured: true,
      cloudConfigured: true,
      method: 'application-default',
    }),
    execute: async (
      operation: GuidedOperation,
      request: OperationRequest,
      context: ProviderContext,
    ) => {
      await context.progress({
        stage: 'fixture',
        message: `Running ${operation}`,
        percent: 50,
      });
      context.write(`project=${request.projectId}`);
      return { operation };
    },
  };
}

async function appFixture() {
  const directory = await temporaryDirectory();
  return {
    ...createApp({
      provider: fakeProvider(),
      operationStore: new OperationStore(path.join(directory, 'operations.json')),
      credentialsPath: path.join(directory, 'credentials.env'),
      csrfToken: 'csrf-test',
      environment: {},
    }),
    directory,
  };
}

describe('local server security', () => {
  it('returns security headers and no credential values', async () => {
    const { app } = await appFixture();
    const response = await request(app).get('/api/bootstrap').expect(200);
    expect(response.headers['x-powered-by']).toBeUndefined();
    expect(response.headers['cache-control']).toBe('no-store');
    expect(response.body.csrfToken).toBe('csrf-test');
    expect(JSON.stringify(response.body.credentials)).not.toContain('secret');
  });

  it('requires both a localhost origin and CSRF token for mutations', async () => {
    const { app } = await appFixture();
    const endpoint = '/api/providers/gcp/operations/discovery';
    await request(app)
      .post(endpoint)
      .set('x-cloud-poc-csrf', 'csrf-test')
      .send({ projectId: 'valid-project1' })
      .expect(403);
    await request(app)
      .post(endpoint)
      .set('Origin', 'https://attacker.example')
      .set('x-cloud-poc-csrf', 'csrf-test')
      .send({ projectId: 'valid-project1' })
      .expect(403);
    await request(app)
      .post(endpoint)
      .set('Origin', 'http://127.0.0.1:5173')
      .send({ projectId: 'valid-project1' })
      .expect(403);
  });

  it('accepts only named operations and requires apply confirmation', async () => {
    const { app } = await appFixture();
    const headers = {
      Origin: 'http://localhost:5173',
      'x-cloud-poc-csrf': 'csrf-test',
    };
    await request(app)
      .post('/api/providers/gcp/operations/shell')
      .set(headers)
      .send({ projectId: 'valid-project1' })
      .expect(404);
    await request(app)
      .post('/api/providers/gcp/operations/terraform-apply')
      .set(headers)
      .send({ projectId: 'valid-project1' })
      .expect(400);
  });

  it('redacts environment and structured secrets', () => {
    const value = 'very-secret-value';
    expect(
      redact(
        `Authorization: Bearer abc {"token":"${value}"} ${value}`,
        { EC_API_KEY: value },
      ),
    ).toBe('Authorization: Bearer [REDACTED] {"token":"[REDACTED]"} [REDACTED]');
  });
});

describe('owner-only local files', () => {
  it('persists credentials with mode 0600 and returns status only', async () => {
    const directory = await temporaryDirectory();
    const filePath = path.join(directory, 'credentials.env');
    const environment: NodeJS.ProcessEnv = {};
    const status = await saveCredentials(
      filePath,
      {
        elasticCloudApiKey: 'elastic-test-secret',
        applicationCredentialsPath: '/home/user/gcp-adc.json',
        impersonateServiceAccount: '',
      },
      environment,
    );
    expect((await fs.stat(filePath)).mode & 0o777).toBe(0o600);
    expect(status).toEqual({
      elasticConfigured: true,
      cloudConfigured: true,
      method: 'application-default',
    });
    expect(JSON.stringify(status)).not.toContain('elastic-test-secret');
  });
});

describe('persisted operation state', () => {
  it('records progress and terminal state in an owner-only file', async () => {
    const directory = await temporaryDirectory();
    const filePath = path.join(directory, 'operations.json');
    const store = new OperationStore(filePath);
    const record = await store.start('analysis', async (context) => {
      await context.progress({
        stage: 'validating',
        message: 'Checking fixtures',
        percent: 80,
      });
      return { findingCount: 2 };
    });
    await new Promise<void>((resolve) => {
      if (store.get(record.id)?.state === 'succeeded') {
        resolve();
        return;
      }
      const listener = (updated: { state: string }) => {
        if (updated.state === 'succeeded') {
          store.events.off(record.id, listener);
          resolve();
        }
      };
      store.events.on(record.id, listener);
    });
    expect(store.get(record.id)?.state).toBe('succeeded');
    expect(store.get(record.id)?.result).toEqual({ findingCount: 2 });
    expect((await fs.stat(filePath)).mode & 0o777).toBe(0o600);

    const restored = new OperationStore(filePath);
    await restored.load();
    expect(restored.get(record.id)?.state).toBe('succeeded');
  });

  it('marks interrupted operations failed on restart', async () => {
    const directory = await temporaryDirectory();
    const filePath = path.join(directory, 'operations.json');
    await fs.writeFile(
      filePath,
      JSON.stringify([
        {
          id: 'old',
          provider: 'gcp',
          operation: 'discovery',
          state: 'running',
          stage: 'inventory',
          message: 'Reading',
          startedAt: '2026-01-01T00:00:00Z',
          updatedAt: '2026-01-01T00:00:00Z',
          logs: [],
        },
      ]),
    );
    const restored = new OperationStore(filePath);
    await restored.load();
    expect(restored.get('old')?.state).toBe('failed');
    expect(restored.get('old')?.stage).toBe('interrupted');
  });
});
