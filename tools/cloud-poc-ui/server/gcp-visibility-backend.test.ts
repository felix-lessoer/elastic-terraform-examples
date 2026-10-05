import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import {
  GcpVisibilityBackend,
  type GcpVisibilityExecutor,
} from './gcp-visibility-backend.js';
import type { VisibilityCandidate } from './visibility.js';

const directories: string[] = [];
afterEach(async () => {
  await Promise.all(
    directories.splice(0).map((directory) =>
      fs.rm(directory, { recursive: true, force: true }),
    ),
  );
});

const candidate: VisibilityCandidate = {
  id: 'cloud-sql-insights:bound',
  name: 'orders',
  resourceId:
    '//sqladmin.googleapis.com/projects/sample-project1/instances/orders',
  resourceType: 'sqladmin.googleapis.com/Instance',
  kind: 'cloud-sql-insights',
  eligibility: 'eligible',
  cost: { gcp: 'overhead', elastic: 'ingest' },
  workloadImpact: 'Enables Query Insights',
  validation: 'Queries a named resource signal',
  rollback: 'Restores the prior setting',
};

class Executor implements GcpVisibilityExecutor {
  calls: string[] = [];

  async describeCloudSql(target: { projectId: string; instance: string }) {
    this.calls.push(`describe:${target.projectId}/${target.instance}`);
    return { queryInsightsEnabled: false };
  }
  async setCloudSqlQueryInsights(
    target: { projectId: string; instance: string },
    enabled: boolean,
  ) {
    this.calls.push(`set:${target.projectId}/${target.instance}:${enabled}`);
  }
  async hasNamedCloudSqlSignal(selected: VisibilityCandidate) {
    this.calls.push(`signal:${selected.resourceId}`);
    return true;
  }
}

describe('allow-listed GCP visibility backend', () => {
  it('marks every adapter unavailable when required signal configuration is absent', () => {
    const backend = GcpVisibilityBackend.fromEnvironment('/tmp/managed.json', {});
    expect(backend.availability(candidate)).toMatchObject({
      supported: false,
      reason: expect.stringContaining('CLOUD_POC_VISIBILITY_ELASTICSEARCH_URL'),
    });
    expect(
      backend.availability({ ...candidate, kind: 'cloud-run-traces' }),
    ).toMatchObject({
      supported: false,
      reason: expect.stringContaining('instrumentation'),
    });
  });

  it('uses only the canonical Cloud SQL target and restores its snapshot', async () => {
    const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'visibility-backend-'));
    directories.push(directory);
    const managedPath = path.join(directory, 'managed.json');
    const executor = new Executor();
    const backend = new GcpVisibilityBackend(managedPath, executor, undefined);
    const snapshot = await backend.snapshot(candidate);
    const { deploymentId } = await backend.deploy(candidate, snapshot);
    expect(await backend.validate(candidate)).toBe(true);
    await backend.rollback(candidate, snapshot, deploymentId);
    expect(executor.calls).toEqual([
      'describe:sample-project1/orders',
      'set:sample-project1/orders:true',
      `signal:${candidate.resourceId}`,
      'set:sample-project1/orders:false',
    ]);
    expect((await fs.stat(managedPath)).mode & 0o777).toBe(0o600);
  });

  it('refuses a non-canonical or mismatched resource target', async () => {
    const executor = new Executor();
    const backend = new GcpVisibilityBackend('/tmp/unused.json', executor, undefined);
    await expect(
      backend.snapshot({
        ...candidate,
        resourceId: '//run.googleapis.com/projects/p/services/orders',
      }),
    ).rejects.toThrow('canonical Cloud SQL');
    expect(executor.calls).toEqual([]);
  });
});
