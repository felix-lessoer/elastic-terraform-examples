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
import {
  loadCredentialEnvironment,
  saveCredentials,
} from './credentials.js';
import { OperationStore } from './operation-store.js';
import {
  GcpVisibilityService,
  type VisibilityBackend,
  type VisibilityCandidate,
  type VisibilitySnapshot,
  visibilityCandidateId,
} from './visibility.js';

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

class ApiVisibilityBackend implements VisibilityBackend {
  calls: string[] = [];
  managed: string[] = [];

  availability(): { supported: boolean } {
    return { supported: true };
  }
  async snapshot(): Promise<VisibilitySnapshot> {
    this.calls.push('snapshot');
    return { version: '1.0', values: { queryInsightsEnabled: false } };
  }
  async deploy(candidate: VisibilityCandidate) {
    this.calls.push(`deploy:${candidate.resourceId}`);
    this.managed = [candidate.id];
    return { deploymentId: candidate.id };
  }
  async validate(candidate: VisibilityCandidate): Promise<boolean> {
    this.calls.push(`validate:${candidate.resourceId}`);
    return true;
  }
  async rollback(candidate: VisibilityCandidate): Promise<void> {
    this.calls.push(`rollback:${candidate.resourceId}`);
    this.managed = [];
  }
  async listManagedDeployments(): Promise<string[]> {
    return this.managed;
  }
  async cleanupOrphan(id: string): Promise<void> {
    this.calls.push(`cleanup:${id}`);
  }
}

async function visibilityAppFixture() {
  const directory = await temporaryDirectory();
  const resourceId =
    '//sqladmin.googleapis.com/projects/valid-project1/instances/orders';
  const candidate: VisibilityCandidate = {
    id: visibilityCandidateId(resourceId, 'cloud-sql-insights'),
    name: 'orders',
    resourceId,
    resourceType: 'sqladmin.googleapis.com/Instance',
    kind: 'cloud-sql-insights',
    eligibility: 'eligible',
    cost: { gcp: 'Database overhead', elastic: 'Ingest cost' },
    workloadImpact: 'Enables Query Insights',
    validation: 'Queries the named resource signal',
    rollback: 'Restores Query Insights setting',
  };
  const backend = new ApiVisibilityBackend();
  const service = new GcpVisibilityService(
    path.join(directory, 'visibility.json'),
    backend,
  );
  return {
    ...createApp({
      provider: fakeProvider(),
      operationStore: new OperationStore(path.join(directory, 'operations.json')),
      credentialsPath: path.join(directory, 'credentials.env'),
      csrfToken: 'csrf-test',
      environment: {},
      visibility: {
        service,
        loadAnalysis: async () => ({ candidates: [candidate] }),
      },
    }),
    candidate,
    backend,
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

describe('visibility lifecycle API', () => {
  const headers = {
    Origin: 'http://localhost:5603',
    'x-cloud-poc-csrf': 'csrf-test',
  };

  it('binds mutations to exact local candidate IDs and requires approvals', async () => {
    const { app, candidate, backend } = await visibilityAppFixture();
    await request(app)
      .post('/api/providers/gcp/visibility/candidates/arbitrary/deploy')
      .set(headers)
      .send({ costAccepted: true, impactAccepted: true })
      .expect(409);
    await request(app)
      .post(`/api/providers/gcp/visibility/candidates/${candidate.id}/deploy`)
      .set(headers)
      .send({ costAccepted: false, impactAccepted: true })
      .expect(400);
    expect(backend.calls).toEqual([]);
  });

  it('deploys, validates, rolls back, and skips only the selected candidate', async () => {
    const { app, candidate, backend } = await visibilityAppFixture();
    const endpoint = `/api/providers/gcp/visibility/candidates/${candidate.id}`;
    await request(app)
      .post(`${endpoint}/deploy`)
      .set(headers)
      .send({ costAccepted: true, impactAccepted: true })
      .expect(200);
    expect(backend.calls).toEqual([
      'snapshot',
      `deploy:${candidate.resourceId}`,
      `validate:${candidate.resourceId}`,
    ]);
    await request(app).post(`${endpoint}/rollback`).set(headers).send({}).expect(200);
    await request(app)
      .post(`${endpoint}/skip`)
      .set(headers)
      .send({ reason: 'Change window closed' })
      .expect(200);
    expect(backend.calls).toContain(`rollback:${candidate.resourceId}`);
  });

  it('protects adapter mutations with origin and CSRF and confirms cleanup', async () => {
    const { app, candidate, backend } = await visibilityAppFixture();
    const endpoint = `/api/providers/gcp/visibility/candidates/${candidate.id}/skip`;
    await request(app)
      .post(endpoint)
      .set('x-cloud-poc-csrf', 'csrf-test')
      .send({ reason: 'Later' })
      .expect(403);
    backend.managed = ['orphan'];
    await request(app)
      .post('/api/providers/gcp/visibility/orphans/cleanup')
      .set(headers)
      .send({ confirmation: 'wrong' })
      .expect(400);
    await request(app)
      .post('/api/providers/gcp/visibility/orphans/cleanup')
      .set(headers)
      .send({ confirmation: 'CLEANUP ORPHANS' })
      .expect(200);
    expect(backend.calls).toContain('cleanup:orphan');
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

  it('restores saved credentials into a restarted server environment', async () => {
    const directory = await temporaryDirectory();
    const filePath = path.join(directory, 'credentials.env');
    await saveCredentials(
      filePath,
      {
        elasticCloudApiKey: 'elastic-test-secret',
        applicationCredentialsPath: '/home/user/gcp-adc.json',
        impersonateServiceAccount: '',
      },
      {},
    );
    const restartedEnvironment: NodeJS.ProcessEnv = {};
    expect(
      await loadCredentialEnvironment(filePath, restartedEnvironment),
    ).toMatchObject({
      elasticConfigured: true,
      cloudConfigured: true,
      method: 'application-default',
    });
    expect(restartedEnvironment).toMatchObject({
      EC_API_KEY: 'elastic-test-secret',
      GOOGLE_APPLICATION_CREDENTIALS: '/home/user/gcp-adc.json',
      CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE: '/home/user/gcp-adc.json',
    });
  });

  it('stores an uploaded Google credential JSON in an owner-only local file', async () => {
    const directory = await temporaryDirectory();
    const filePath = path.join(directory, 'credentials.env');
    const environment: NodeJS.ProcessEnv = {};
    await saveCredentials(
      filePath,
      {
        elasticCloudApiKey: 'elastic-test-secret',
        applicationCredentialsPath: '',
        applicationCredentialsJson: JSON.stringify({
          type: 'service_account',
          project_id: 'valid-project1',
          private_key_id: 'key-id',
          private_key: 'private-test-secret',
          client_email: 'terraform@valid-project1.iam.gserviceaccount.com',
          client_id: '123',
          token_uri: 'https://oauth2.googleapis.com/token',
        }),
        impersonateServiceAccount: '',
      },
      environment,
    );
    const uploadedPath = path.join(
      directory,
      'gcp-application-credentials.json',
    );
    expect((await fs.stat(uploadedPath)).mode & 0o777).toBe(0o600);
    expect(environment.GOOGLE_APPLICATION_CREDENTIALS).toBe(uploadedPath);
    expect(environment.CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE).toBe(
      uploadedPath,
    );
  });

  it('rejects workstation paths that do not exist in the Cloud Agent VM', async () => {
    const directory = await temporaryDirectory();
    await expect(
      saveCredentials(
        path.join(directory, 'credentials.env'),
        {
          elasticCloudApiKey: 'elastic-test-secret',
          applicationCredentialsPath:
            'C:\\Users\\operator\\Downloads\\gcp.json',
          applicationCredentialsJson: '',
          impersonateServiceAccount: '',
        },
        {},
      ),
    ).rejects.toThrow(
      'upload a credential JSON when using a forwarded Cloud Agent UI',
    );
  });
});

describe('persisted operation state', () => {
  it('records progress and terminal state in an owner-only file', async () => {
    const directory = await temporaryDirectory();
    const filePath = path.join(directory, 'operations.json');
    const store = new OperationStore(filePath);
    const record = await store.start(
      'analysis',
      async (context) => {
        await context.progress({
          stage: 'validating',
          message: 'Checking fixtures',
          percent: 80,
        });
        return { findingCount: 2 };
      },
      'valid-project1',
    );
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
    expect(store.get(record.id)?.projectId).toBe('valid-project1');
    expect(store.get(record.id)?.result).toEqual({ findingCount: 2 });
    expect((await fs.stat(filePath)).mode & 0o777).toBe(0o600);

    const restored = new OperationStore(filePath);
    await restored.load();
    expect(restored.get(record.id)?.state).toBe('succeeded');
    expect(restored.get(record.id)?.projectId).toBe('valid-project1');
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
