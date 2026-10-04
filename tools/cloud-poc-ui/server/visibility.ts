import { createHash } from 'node:crypto';
import { readJson, writeOwnerOnly } from './local-files.js';

export type VisibilityKind =
  | 'cloud-run-traces'
  | 'gke-metrics'
  | 'cloud-sql-insights';

export interface VisibilityCandidate {
  id: string;
  name: string;
  resourceId: string;
  resourceType: string;
  kind: VisibilityKind;
  eligibility: 'eligible' | 'inactive' | 'unsupported';
  reason?: string;
  cost: {
    gcp: string;
    elastic: string;
  };
  workloadImpact: string;
  validation: string;
  rollback: string;
}

export interface VisibilitySnapshot {
  version: '1.0';
  values: Record<string, unknown>;
}

export interface VisibilityBackend {
  availability(candidate: VisibilityCandidate): {
    supported: boolean;
    reason?: string;
  };
  snapshot(candidate: VisibilityCandidate): Promise<VisibilitySnapshot>;
  deploy(
    candidate: VisibilityCandidate,
    snapshot: VisibilitySnapshot,
  ): Promise<{ deploymentId: string }>;
  validate(candidate: VisibilityCandidate, deploymentId: string): Promise<boolean>;
  rollback(
    candidate: VisibilityCandidate,
    snapshot: VisibilitySnapshot,
    deploymentId: string,
  ): Promise<void>;
  listManagedDeployments(): Promise<string[]>;
  cleanupOrphan(deploymentId: string): Promise<void>;
}

export interface VisibilityRecord {
  candidate: VisibilityCandidate;
  state:
    | 'deploying'
    | 'validating'
    | 'deployed'
    | 'skipped'
    | 'rolling-back'
    | 'rolled-back';
  snapshot?: VisibilitySnapshot;
  deploymentId?: string;
  reason?: string;
  updatedAt: string;
}

interface VisibilityState {
  schemaVersion: '1.0';
  records: Record<string, VisibilityRecord>;
}

const mapping: Record<
  string,
  Omit<VisibilityCandidate, 'id' | 'name' | 'resourceId' | 'resourceType' | 'eligibility'>
> = {
  'run.googleapis.com/Service': {
    kind: 'cloud-run-traces',
    cost: {
      gcp: 'May add CPU, memory, and outbound telemetry charges.',
      elastic: 'Trace ingest and retention increase with request volume.',
    },
    workloadImpact: 'Creates a new revision with explicit tracing environment configuration.',
    validation: 'Send a normal request and confirm a fresh trace for this service.',
    rollback: 'Restore the snapshotted revision configuration and route traffic back.',
  },
  'container.googleapis.com/Cluster': {
    kind: 'gke-metrics',
    cost: {
      gcp: 'Adds a small collector workload and telemetry egress.',
      elastic: 'Metrics ingest and retention increase with cluster size.',
    },
    workloadImpact: 'Deploys a namespaced OpenTelemetry collector with narrow RBAC.',
    validation: 'Confirm fresh cluster metrics from the named cluster.',
    rollback: 'Delete the adapter namespace and its dedicated RBAC resources.',
  },
  'sqladmin.googleapis.com/Instance': {
    kind: 'cloud-sql-insights',
    cost: {
      gcp: 'Query Insights may add database overhead and provider charges.',
      elastic: 'Database telemetry increases ingest and retention.',
    },
    workloadImpact: 'Updates the named instance flags; a restart may be required.',
    validation: 'Confirm fresh database telemetry for the named instance.',
    rollback: 'Restore the exact snapshotted database flags.',
  },
};

export function visibilityCandidateId(
  resourceId: string,
  kind: VisibilityKind,
): string {
  return `${kind}:${createHash('sha256').update(resourceId).digest('hex').slice(0, 24)}`;
}

export function candidatesFromResources(
  resources: Array<{ id: string; name: string; type: string; state: string }>,
): VisibilityCandidate[] {
  return resources.flatMap((resource) => {
    const definition = mapping[resource.type];
    if (!definition) return [];
    const active =
      !resource.state ||
      ['ACTIVE', 'RUNNING', 'READY', 'UNKNOWN'].includes(
        resource.state.toUpperCase(),
      );
    return [
      {
        id: visibilityCandidateId(resource.id, definition.kind),
        name: resource.name,
        resourceId: resource.id,
        resourceType: resource.type,
        eligibility: active ? 'eligible' : 'inactive',
        reason: active ? undefined : `Resource state is ${resource.state}`,
        ...definition,
      },
    ];
  });
}

export class GcpVisibilityService {
  private state: VisibilityState = { schemaVersion: '1.0', records: {} };
  private loaded = false;

  constructor(
    private readonly statePath: string,
    private readonly backend: VisibilityBackend,
  ) {}

  prepare(candidate: VisibilityCandidate): VisibilityCandidate {
    if (candidate.eligibility !== 'eligible') return candidate;
    const availability = this.backend.availability(candidate);
    return availability.supported
      ? candidate
      : {
          ...candidate,
          eligibility: 'unsupported',
          reason:
            availability.reason ?? 'No safe adapter is available for this candidate',
        };
  }

  async records(): Promise<VisibilityRecord[]> {
    await this.load();
    return Object.values(this.state.records);
  }

  async deploy(
    candidate: VisibilityCandidate,
    approval: { costAccepted: boolean; impactAccepted: boolean },
  ): Promise<VisibilityRecord> {
    await this.load();
    if (candidate.eligibility !== 'eligible') {
      return this.skip(candidate, candidate.reason ?? candidate.eligibility);
    }
    if (!approval.costAccepted || !approval.impactAccepted) {
      throw new Error('Acknowledge both cost and workload impact before deployment');
    }
    const existing = this.state.records[candidate.id];
    if (existing?.state === 'deployed') return existing;
    const snapshot = await this.backend.snapshot(candidate);
    let record = await this.save({
      candidate,
      state: 'deploying',
      snapshot,
      updatedAt: new Date().toISOString(),
    });
    const deployed = await this.backend.deploy(candidate, snapshot);
    record = await this.save({
      ...record,
      state: 'validating',
      deploymentId: deployed.deploymentId,
      updatedAt: new Date().toISOString(),
    });
    let validated = false;
    let validationError: string | undefined;
    try {
      validated = await this.backend.validate(candidate, deployed.deploymentId);
    } catch (error) {
      validationError = error instanceof Error ? error.message : String(error);
    }
    if (!validated) {
      await this.backend.rollback(candidate, snapshot, deployed.deploymentId);
      return this.save({
        ...record,
        state: 'rolled-back',
        reason: validationError
          ? `Signal validation could not complete (${validationError}); the snapshot was restored`
          : 'Signal validation failed; the snapshot was restored',
        updatedAt: new Date().toISOString(),
      });
    }
    return this.save({
      ...record,
      state: 'deployed',
      updatedAt: new Date().toISOString(),
    });
  }

  async rollback(candidateId: string): Promise<VisibilityRecord> {
    await this.load();
    const record = this.state.records[candidateId];
    if (!record) throw new Error('No visibility adapter state exists');
    if (record.state === 'rolled-back' || record.state === 'skipped') return record;
    if (!record.snapshot || !record.deploymentId) {
      throw new Error('Rollback state is incomplete; do not mutate the workload');
    }
    await this.save({
      ...record,
      state: 'rolling-back',
      updatedAt: new Date().toISOString(),
    });
    await this.backend.rollback(
      record.candidate,
      record.snapshot,
      record.deploymentId,
    );
    return this.save({
      ...record,
      state: 'rolled-back',
      updatedAt: new Date().toISOString(),
    });
  }

  async skip(
    candidate: VisibilityCandidate,
    reason: string,
  ): Promise<VisibilityRecord> {
    await this.load();
    if (!reason.trim()) throw new Error('A skip reason is required');
    return this.save({
      candidate,
      state: 'skipped',
      reason,
      updatedAt: new Date().toISOString(),
    });
  }

  async cleanupOrphans(): Promise<string[]> {
    await this.load();
    const tracked = new Set(
      Object.values(this.state.records)
        .filter((record) => record.state === 'deployed')
        .map((record) => record.deploymentId)
        .filter((id): id is string => Boolean(id)),
    );
    const orphaned = (await this.backend.listManagedDeployments()).filter(
      (id) => !tracked.has(id),
    );
    for (const id of orphaned) await this.backend.cleanupOrphan(id);
    return orphaned;
  }

  private async load(): Promise<void> {
    if (this.loaded) return;
    this.state = await readJson(this.statePath, this.state);
    this.loaded = true;
  }

  private async save(record: VisibilityRecord): Promise<VisibilityRecord> {
    this.state.records[record.candidate.id] = record;
    await writeOwnerOnly(
      this.statePath,
      `${JSON.stringify(this.state, null, 2)}\n`,
    );
    return record;
  }
}
