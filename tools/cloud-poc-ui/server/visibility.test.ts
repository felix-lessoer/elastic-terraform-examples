import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import {
  GcpVisibilityService,
  type VisibilityBackend,
  type VisibilityCandidate,
  type VisibilitySnapshot,
} from './visibility.js';

class FixtureBackend implements VisibilityBackend {
  calls: string[] = [];
  valid = true;
  validationError = false;
  managed = ['managed-1'];

  availability(): { supported: boolean } {
    return { supported: true };
  }

  async snapshot(): Promise<VisibilitySnapshot> {
    this.calls.push('snapshot');
    return { version: '1.0', values: { revision: 'original' } };
  }

  async deploy(): Promise<{ deploymentId: string }> {
    this.calls.push('deploy');
    return { deploymentId: 'managed-1' };
  }

  async validate(): Promise<boolean> {
    this.calls.push('validate');
    if (this.validationError) throw new Error('signal query unavailable');
    return this.valid;
  }

  async rollback(): Promise<void> {
    this.calls.push('rollback');
  }

  async listManagedDeployments(): Promise<string[]> {
    this.calls.push('list');
    return this.managed;
  }

  async cleanupOrphan(id: string): Promise<void> {
    this.calls.push(`cleanup:${id}`);
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
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'gcp-visibility-'));
  directories.push(directory);
  const statePath = path.join(directory, 'visibility.json');
  const backend = new FixtureBackend();
  const service = new GcpVisibilityService(statePath, backend);
  const candidate: VisibilityCandidate = {
    id: 'cloud-run-traces:checkout',
    name: 'checkout',
    resourceId: '//run.googleapis.com/services/checkout',
    resourceType: 'run.googleapis.com/Service',
    kind: 'cloud-run-traces',
    eligibility: 'eligible',
    cost: {
      gcp: 'CPU and network cost',
      elastic: 'Trace ingest cost',
    },
    workloadImpact: 'Creates a revision',
    validation: 'Confirm a fresh trace',
    rollback: 'Restore the revision snapshot',
  };
  return { statePath, backend, service, candidate };
}

describe('GCP optional visibility adapter contract', () => {
  it('requires explicit cost and impact approval', async () => {
    const { service, candidate, backend } = await fixture();
    await expect(
      service.deploy(candidate, {
        costAccepted: false,
        impactAccepted: true,
      }),
    ).rejects.toThrow('Acknowledge both cost');
    expect(backend.calls).toEqual([]);
  });

  it('snapshots, deploys, validates, and persists owner-only rollback state', async () => {
    const { service, candidate, backend, statePath } = await fixture();
    const record = await service.deploy(candidate, {
      costAccepted: true,
      impactAccepted: true,
    });
    expect(record.state).toBe('deployed');
    expect(record.snapshot?.values).toEqual({ revision: 'original' });
    expect(backend.calls).toEqual(['snapshot', 'deploy', 'validate']);
    expect((await fs.stat(statePath)).mode & 0o777).toBe(0o600);
  });

  it('restores the snapshot when signal validation fails', async () => {
    const { service, candidate, backend } = await fixture();
    backend.valid = false;
    const record = await service.deploy(candidate, {
      costAccepted: true,
      impactAccepted: true,
    });
    expect(record.state).toBe('rolled-back');
    expect(record.reason).toContain('validation failed');
    expect(backend.calls).toEqual([
      'snapshot',
      'deploy',
      'validate',
      'rollback',
    ]);
  });

  it('restores the snapshot when the named signal query errors', async () => {
    const { service, candidate, backend } = await fixture();
    backend.validationError = true;
    const record = await service.deploy(candidate, {
      costAccepted: true,
      impactAccepted: true,
    });
    expect(record.state).toBe('rolled-back');
    expect(record.reason).toContain('signal query unavailable');
    expect(backend.calls).toEqual([
      'snapshot',
      'deploy',
      'validate',
      'rollback',
    ]);
  });

  it('supports explicit and automatic skips without mutation', async () => {
    const { service, candidate, backend } = await fixture();
    expect((await service.skip(candidate, 'Change window closed')).state).toBe(
      'skipped',
    );
    const inactive = {
      ...candidate,
      id: 'cloud-run-traces:inactive',
      eligibility: 'inactive' as const,
      reason: 'Resource state is STOPPED',
    };
    expect(
      (
        await service.deploy(inactive, {
          costAccepted: true,
          impactAccepted: true,
        })
      ).reason,
    ).toBe('Resource state is STOPPED');
    expect(backend.calls).toEqual([]);
  });

  it('rolls back idempotently and cleans only untracked managed adapters', async () => {
    const { service, candidate, backend } = await fixture();
    await service.deploy(candidate, {
      costAccepted: true,
      impactAccepted: true,
    });
    expect((await service.rollback(candidate.id)).state).toBe('rolled-back');
    expect((await service.rollback(candidate.id)).state).toBe('rolled-back');
    backend.managed = ['managed-1', 'orphan-2'];
    expect(await service.cleanupOrphans()).toEqual(['managed-1', 'orphan-2']);
    expect(backend.calls.filter((call) => call === 'rollback')).toHaveLength(1);
    expect(backend.calls).toContain('cleanup:orphan-2');
  });
});
