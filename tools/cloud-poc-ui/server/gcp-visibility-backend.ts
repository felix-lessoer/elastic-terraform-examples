import { execa } from 'execa';
import { z } from 'zod';
import { readJson, writeOwnerOnly } from './local-files.js';
import type {
  VisibilityBackend,
  VisibilityCandidate,
  VisibilitySnapshot,
} from './visibility.js';

interface CloudSqlTarget {
  projectId: string;
  instance: string;
}

interface ManagedDeployment {
  candidate: VisibilityCandidate;
  snapshot: VisibilitySnapshot;
}

type ManagedDeployments = Record<string, ManagedDeployment>;

export interface GcpVisibilityExecutor {
  describeCloudSql(target: CloudSqlTarget): Promise<{ queryInsightsEnabled: boolean }>;
  setCloudSqlQueryInsights(target: CloudSqlTarget, enabled: boolean): Promise<void>;
  hasNamedCloudSqlSignal(candidate: VisibilityCandidate): Promise<boolean>;
}

const segment = /^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$/;
const project = /^[a-z][a-z0-9-]{4,61}[a-z0-9]$/;
const index = /^[a-zA-Z0-9_*.-]{1,255}$/;

function cloudSqlTarget(candidate: VisibilityCandidate): CloudSqlTarget {
  const match = candidate.resourceId.match(
    /^\/\/sqladmin\.googleapis\.com\/projects\/([^/]+)\/instances\/([^/]+)$/,
  );
  if (
    !match ||
    candidate.resourceType !== 'sqladmin.googleapis.com/Instance' ||
    !project.test(match[1]) ||
    !segment.test(match[2])
  ) {
    throw new Error('The candidate is not a canonical Cloud SQL instance resource');
  }
  return { projectId: match[1], instance: match[2] };
}

export class ProductionGcpVisibilityExecutor implements GcpVisibilityExecutor {
  constructor(
    private readonly elasticsearchUrl: string,
    private readonly elasticsearchApiKey: string,
    private readonly elasticsearchIndex: string,
  ) {}

  async describeCloudSql(
    target: CloudSqlTarget,
  ): Promise<{ queryInsightsEnabled: boolean }> {
    const result = await execa(
      'gcloud',
      [
        'sql',
        'instances',
        'describe',
        target.instance,
        `--project=${target.projectId}`,
        '--format=json(settings.insightsConfig.queryInsightsEnabled)',
      ],
      { reject: false, stdin: 'ignore', timeout: 30_000 },
    );
    if (result.exitCode !== 0) {
      throw new Error('Unable to read the named Cloud SQL instance');
    }
    const value = z
      .object({
        settings: z
          .object({
            insightsConfig: z
              .object({ queryInsightsEnabled: z.boolean().optional() })
              .optional(),
          })
          .optional(),
      })
      .parse(JSON.parse(result.stdout));
    return {
      queryInsightsEnabled:
        value.settings?.insightsConfig?.queryInsightsEnabled ?? false,
    };
  }

  async setCloudSqlQueryInsights(
    target: CloudSqlTarget,
    enabled: boolean,
  ): Promise<void> {
    const result = await execa(
      'gcloud',
      [
        'sql',
        'instances',
        'patch',
        target.instance,
        `--project=${target.projectId}`,
        enabled
          ? '--insights-config-query-insights-enabled'
          : '--no-insights-config-query-insights-enabled',
        '--quiet',
      ],
      { reject: false, stdin: 'ignore', timeout: 600_000 },
    );
    if (result.exitCode !== 0) {
      throw new Error('Cloud SQL rejected the fixed Query Insights update');
    }
  }

  async hasNamedCloudSqlSignal(candidate: VisibilityCandidate): Promise<boolean> {
    const target = cloudSqlTarget(candidate);
    const url = new URL(
      `${this.elasticsearchUrl.replace(/\/+$/, '')}/${this.elasticsearchIndex}/_search`,
    );
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        Authorization: `ApiKey ${this.elasticsearchApiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        size: 0,
        track_total_hits: 1,
        query: {
          bool: {
            filter: [{ range: { '@timestamp': { gte: 'now-15m' } } }],
            minimum_should_match: 1,
            should: [
              { term: { 'resource.id': candidate.resourceId } },
              {
                term: {
                  'gcp.cloudsql.database_id': `${target.projectId}:${target.instance}`,
                },
              },
              {
                bool: {
                  filter: [
                    { term: { 'cloud.account.id': target.projectId } },
                    { term: { 'cloud.instance.id': target.instance } },
                  ],
                },
              },
            ],
          },
        },
      }),
      signal: AbortSignal.timeout(30_000),
    });
    if (!response.ok) {
      throw new Error('Elasticsearch rejected the named Cloud SQL signal query');
    }
    const body = z
      .object({
        hits: z.object({
          total: z.union([
            z.number(),
            z.object({ value: z.number() }),
          ]),
        }),
      })
      .parse(await response.json());
    const total =
      typeof body.hits.total === 'number'
        ? body.hits.total
        : body.hits.total.value;
    return total > 0;
  }
}

export class GcpVisibilityBackend implements VisibilityBackend {
  constructor(
    private readonly managedPath: string,
    private readonly executor: GcpVisibilityExecutor | undefined,
    private readonly unavailableReason: string | undefined,
  ) {}

  static fromEnvironment(
    managedPath: string,
    environment: NodeJS.ProcessEnv = process.env,
  ): GcpVisibilityBackend {
    const url = environment.CLOUD_POC_VISIBILITY_ELASTICSEARCH_URL;
    const apiKey = environment.CLOUD_POC_VISIBILITY_ELASTICSEARCH_API_KEY;
    const indexName = environment.CLOUD_POC_VISIBILITY_ELASTICSEARCH_INDEX;
    if (!url || !apiKey || !indexName) {
      return new GcpVisibilityBackend(
        managedPath,
        undefined,
        'Set CLOUD_POC_VISIBILITY_ELASTICSEARCH_URL, CLOUD_POC_VISIBILITY_ELASTICSEARCH_API_KEY, and CLOUD_POC_VISIBILITY_ELASTICSEARCH_INDEX; the API key must query the existing Google Cloud integration.',
      );
    }
    let parsedUrl: URL;
    try {
      parsedUrl = new URL(url);
    } catch {
      return new GcpVisibilityBackend(
        managedPath,
        undefined,
        'CLOUD_POC_VISIBILITY_ELASTICSEARCH_URL must be a valid HTTPS URL.',
      );
    }
    if (parsedUrl.protocol !== 'https:' || !index.test(indexName)) {
      return new GcpVisibilityBackend(
        managedPath,
        undefined,
        'The visibility Elasticsearch URL must use HTTPS and its index must contain only letters, digits, _, *, ., or -.',
      );
    }
    return new GcpVisibilityBackend(
      managedPath,
      new ProductionGcpVisibilityExecutor(url, apiKey, indexName),
      undefined,
    );
  }

  availability(candidate: VisibilityCandidate): { supported: boolean; reason?: string } {
    if (candidate.kind === 'cloud-run-traces') {
      return {
        supported: false,
        reason:
          'Cloud Run tracing is unsupported: this repository has no contract for safely installing application instrumentation and restoring revision traffic.',
      };
    }
    if (candidate.kind === 'gke-metrics') {
      return {
        supported: false,
        reason:
          'GKE metrics is unsupported: this repository has no reviewed collector manifest, narrow RBAC contract, or safe cluster rollback implementation.',
      };
    }
    try {
      cloudSqlTarget(candidate);
    } catch (error) {
      return {
        supported: false,
        reason: error instanceof Error ? error.message : String(error),
      };
    }
    return this.executor
      ? { supported: true }
      : { supported: false, reason: this.unavailableReason };
  }

  async snapshot(candidate: VisibilityCandidate): Promise<VisibilitySnapshot> {
    const executor = this.requireExecutor(candidate);
    return {
      version: '1.0',
      values: await executor.describeCloudSql(cloudSqlTarget(candidate)),
    };
  }

  async deploy(
    candidate: VisibilityCandidate,
    snapshot: VisibilitySnapshot,
  ): Promise<{ deploymentId: string }> {
    const executor = this.requireExecutor(candidate);
    const target = cloudSqlTarget(candidate);
    await executor.setCloudSqlQueryInsights(target, true);
    const deploymentId = candidate.id;
    try {
      const managed = await readJson<ManagedDeployments>(this.managedPath, {});
      managed[deploymentId] = { candidate, snapshot };
      await writeOwnerOnly(
        this.managedPath,
        `${JSON.stringify(managed, null, 2)}\n`,
      );
    } catch (error) {
      const value = z
        .object({ queryInsightsEnabled: z.boolean() })
        .parse(snapshot.values);
      await executor.setCloudSqlQueryInsights(
        target,
        value.queryInsightsEnabled,
      );
      throw error;
    }
    return { deploymentId };
  }

  async validate(candidate: VisibilityCandidate): Promise<boolean> {
    return this.requireExecutor(candidate).hasNamedCloudSqlSignal(candidate);
  }

  async rollback(
    candidate: VisibilityCandidate,
    snapshot: VisibilitySnapshot,
    deploymentId: string,
  ): Promise<void> {
    const executor = this.requireExecutor(candidate);
    const value = z
      .object({ queryInsightsEnabled: z.boolean() })
      .parse(snapshot.values);
    await executor.setCloudSqlQueryInsights(
      cloudSqlTarget(candidate),
      value.queryInsightsEnabled,
    );
    const managed = await readJson<ManagedDeployments>(this.managedPath, {});
    delete managed[deploymentId];
    await writeOwnerOnly(this.managedPath, `${JSON.stringify(managed, null, 2)}\n`);
  }

  async listManagedDeployments(): Promise<string[]> {
    return Object.keys(await readJson<ManagedDeployments>(this.managedPath, {}));
  }

  async cleanupOrphan(deploymentId: string): Promise<void> {
    const managed = await readJson<ManagedDeployments>(this.managedPath, {});
    const deployment = managed[deploymentId];
    if (!deployment) return;
    await this.rollback(
      deployment.candidate,
      deployment.snapshot,
      deploymentId,
    );
  }

  private requireExecutor(candidate: VisibilityCandidate): GcpVisibilityExecutor {
    const availability = this.availability(candidate);
    if (!availability.supported || !this.executor) {
      throw new Error(availability.reason ?? 'Visibility adapter is unavailable');
    }
    return this.executor;
  }
}
