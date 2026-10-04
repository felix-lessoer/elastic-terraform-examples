import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import type { ProviderContext } from '../cloud-provider.js';
import type {
  CommandId,
  CommandResult,
  CommandRunner,
} from '../commands.js';
import { GcpProvider } from './gcp.js';

class FixtureRunner implements CommandRunner {
  readonly calls: Array<{ id: CommandId; values: Record<string, string> }> = [];

  async run(
    id: CommandId,
    values: Record<string, string>,
  ): Promise<CommandResult> {
    this.calls.push({ id, values });
    if (id === 'gcp.discover') {
      const manifest = {
        schema_version: '1.0',
        generated_at: '2026-10-04T12:00:00Z',
        approved_projects: [values.projectId],
        limits: {},
        operation_results: [],
        summary: {
          complete: true,
          resources: 1,
          statuses: { success: 1 },
        },
        resources: [
          {
            project_id: values.projectId,
            kind: 'asset',
            resource_id:
              '//run.googleapis.com/projects/test/locations/europe/services/api',
            display_name: 'checkout-api',
            asset_type: 'run.googleapis.com/Service',
            state: 'READY',
          },
        ],
      };
      await fs.mkdir(path.dirname(values.manifestPath), {
        recursive: true,
        mode: 0o700,
      });
      await fs.writeFile(
        values.manifestPath,
        `${JSON.stringify(manifest)}\n`,
        { mode: 0o600 },
      );
      return {
        exitCode: 0,
        stdout: JSON.stringify({
          manifest_sha256: 'a'.repeat(64),
          summary: manifest.summary,
        }),
        stderr: '',
      };
    }
    const output: Partial<Record<CommandId, unknown>> = {
      'terraform.version': { terraform_version: '1.16.5' },
      'gcloud.version': { 'Google Cloud SDK': '540.0.0' },
      'gcp.identity': {
        projectId: values.projectId,
        projectNumber: '123',
        lifecycleState: 'ACTIVE',
      },
      'terraform.show': {
        timestamp: '2026-10-04T12:00:00Z',
        resource_changes: [
          {
            address: 'google_project_service.asset',
            mode: 'managed',
            type: 'google_project_service',
            name: 'asset',
            change: {
              actions: ['create'],
              after: { private_key: 'must-not-leak' },
            },
          },
        ],
      },
    };
    return {
      exitCode: 0,
      stdout: JSON.stringify(output[id] ?? {}),
      stderr: '',
    };
  }
}

const directories: string[] = [];
afterEach(async () => {
  await Promise.all(
    directories.splice(0).map((directory) =>
      fs.rm(directory, { recursive: true, force: true }),
    ),
  );
});

async function fixture() {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'gcp-provider-'));
  directories.push(directory);
  const runner = new FixtureRunner();
  const updates: string[] = [];
  const context: ProviderContext = {
    write: () => undefined,
    progress: async (update) => {
      updates.push(update.stage);
    },
  };
  const provider = new GcpProvider(
    directory,
    path.join(directory, 'artifacts'),
    runner,
    async () => ({
      elasticConfigured: true,
      cloudConfigured: true,
      method: 'impersonation',
    }),
    { GCP_POC_COCKPIT_URL: 'https://kibana.example/app/dashboards' },
  );
  return { directory, runner, updates, context, provider };
}

describe('GCP provider', () => {
  it('runs identity preflight through the fixed command contract', async () => {
    const { provider, runner, context } = await fixture();
    const result = await provider.execute(
      'preflight',
      { projectId: 'sample-project1' },
      context,
    );
    expect(runner.calls).toEqual([
      { id: 'terraform.version', values: {} },
      { id: 'gcloud.version', values: {} },
      { id: 'gcp.identity', values: { projectId: 'sample-project1' } },
    ]);
    expect(result).toMatchObject({
      identity: { projectId: 'sample-project1' },
    });
  });

  it('persists a bounded local discovery manifest and creates named candidates', async () => {
    const { provider, context, directory } = await fixture();
    const discovery = await provider.execute(
      'discovery',
      { projectId: 'sample-project1' },
      context,
    );
    expect(discovery).toMatchObject({
      resourceCount: 1,
      partial: false,
      manifestVersion: '1.0',
    });
    const manifestPath = path.join(directory, 'artifacts/gcp-manifest.json');
    expect((await fs.stat(manifestPath)).mode & 0o777).toBe(0o600);

    const analysis = (await provider.execute(
      'analysis',
      { projectId: 'sample-project1' },
      context,
    )) as { candidates: Array<{ name: string; cost: unknown; workloadImpact: string }> };
    expect(analysis.candidates[0]).toMatchObject({
      name: 'checkout-api',
      cost: {
        gcp: expect.any(String),
        elastic: expect.any(String),
      },
      workloadImpact: expect.any(String),
    });
  });

  it('returns readable plan actions without planned values', async () => {
    const { provider, runner, context } = await fixture();
    const result = await provider.execute(
      'terraform-plan',
      { projectId: 'sample-project1' },
      context,
    );
    expect(runner.calls.map((call) => call.id)).toEqual([
      'terraform.plan',
      'terraform.show',
    ]);
    expect(result).toMatchObject({
      counts: { create: 1 },
      resources: [
        {
          action: 'create',
          label: 'Create google_project_service.asset',
        },
      ],
    });
    expect(JSON.stringify(result)).not.toContain('must-not-leak');
  });

  it('allow-lists workflow IDs and emits safe final links', async () => {
    const { provider, context } = await fixture();
    await expect(
      provider.execute(
        'workflows',
        {
          projectId: 'sample-project1',
          workflowIds: ['unapproved-workflow'],
        },
        context,
      ),
    ).rejects.toThrow('Unknown GCP workflow');
    expect(
      await provider.execute(
        'final-links',
        { projectId: 'sample-project1' },
        context,
      ),
    ).toEqual({
      cockpit: 'https://kibana.example/app/dashboards',
      cloudConsole:
        'https://console.cloud.google.com/home/dashboard?project=sample-project1',
    });
  });
});
