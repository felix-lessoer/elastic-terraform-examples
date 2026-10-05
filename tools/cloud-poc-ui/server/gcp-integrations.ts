import { createHash } from 'node:crypto';
import { promises as fs } from 'node:fs';
import { z } from 'zod';

export const gcpServiceIds = [
  'cspm',
  'audit',
  'firewall',
  'vpcflow',
  'dns',
  'loadbalancing',
  'compute',
  'storage',
  'gke',
  'cloudrun',
  'cloudsql',
  'pubsub',
  'firestore',
  'dataproc',
  'redis',
  'billing',
] as const;

export const gcpServiceIdSchema = z.enum(gcpServiceIds);
export type GcpServiceId = z.infer<typeof gcpServiceIdSchema>;
export const gcpCoreServiceIds: GcpServiceId[] = [
  'cspm',
  'audit',
  'firewall',
  'vpcflow',
  'dns',
  'loadbalancing',
  'compute',
  'storage',
];

type Definition = {
  id: GcpServiceId;
  name: string;
  mode: 'core' | 'optional';
  assetMarkers: string[];
  apiServices: string[];
  permissions: string;
  gcpCost: string;
  elasticCost: string;
  signals: string[];
};

export type GcpIntegrationRecommendation = Definition & {
  discovered: boolean;
  recommended: boolean;
  selectedByDefault: boolean;
  requiresConfiguration: boolean;
  reason: string;
};

const definitions: Definition[] = [
  {
    id: 'cspm',
    name: 'Cloud Security Posture Management',
    mode: 'core',
    assetMarkers: [],
    apiServices: ['cloudasset.googleapis.com'],
    permissions: 'Cloud Asset Viewer and IAM Security Reviewer',
    gcpCost: 'Read-only asset inventory API usage',
    elasticCost: 'CSPM findings ingest and retention',
    signals: ['assets', 'misconfigurations'],
  },
  {
    id: 'audit',
    name: 'Cloud Audit Logs',
    mode: 'core',
    assetMarkers: [],
    apiServices: ['logging.googleapis.com'],
    permissions: 'Logging sink creation and Pub/Sub publisher/subscriber IAM',
    gcpCost: 'Logging routing and Pub/Sub delivery',
    elasticCost: 'Audit log ingest and retention',
    signals: ['logs'],
  },
  {
    id: 'firewall',
    name: 'Firewall logs',
    mode: 'core',
    assetMarkers: ['compute.googleapis.com/Firewall'],
    apiServices: ['compute.googleapis.com'],
    permissions: 'Logging sink creation and Pub/Sub access',
    gcpCost: 'Firewall logging, routing, and Pub/Sub delivery',
    elasticCost: 'Firewall log ingest and retention',
    signals: ['logs'],
  },
  {
    id: 'vpcflow',
    name: 'VPC Flow logs',
    mode: 'core',
    assetMarkers: ['compute.googleapis.com/Network', 'compute.googleapis.com/Subnetwork'],
    apiServices: ['compute.googleapis.com'],
    permissions: 'Logging sink creation and Pub/Sub access',
    gcpCost: 'VPC Flow Logs must already be enabled; routing and Pub/Sub delivery',
    elasticCost: 'Network log ingest and retention',
    signals: ['logs'],
  },
  {
    id: 'dns',
    name: 'Cloud DNS logs',
    mode: 'core',
    assetMarkers: ['dns.googleapis.com/ManagedZone'],
    apiServices: ['dns.googleapis.com'],
    permissions: 'Logging sink creation and Pub/Sub access',
    gcpCost: 'DNS logging, routing, and Pub/Sub delivery',
    elasticCost: 'DNS log ingest and retention',
    signals: ['logs'],
  },
  {
    id: 'loadbalancing',
    name: 'Cloud Load Balancing',
    mode: 'core',
    assetMarkers: ['compute.googleapis.com/ForwardingRule', 'compute.googleapis.com/BackendService'],
    apiServices: ['compute.googleapis.com'],
    permissions: 'Monitoring Viewer, Logging sink creation, and Pub/Sub access',
    gcpCost: 'Monitoring API reads plus load-balancer log routing',
    elasticCost: 'Metrics and log ingest',
    signals: ['metrics', 'logs'],
  },
  {
    id: 'compute',
    name: 'Compute Engine',
    mode: 'core',
    assetMarkers: ['compute.googleapis.com/Instance'],
    apiServices: ['compute.googleapis.com'],
    permissions: 'Monitoring Viewer',
    gcpCost: 'Cloud Monitoring API reads',
    elasticCost: 'Compute metrics ingest',
    signals: ['metrics'],
  },
  {
    id: 'storage',
    name: 'Cloud Storage',
    mode: 'core',
    assetMarkers: ['storage.googleapis.com/Bucket'],
    apiServices: ['storage.googleapis.com'],
    permissions: 'Monitoring Viewer',
    gcpCost: 'Cloud Monitoring API reads',
    elasticCost: 'Storage metrics ingest',
    signals: ['metrics'],
  },
  {
    id: 'gke',
    name: 'Google Kubernetes Engine',
    mode: 'optional',
    assetMarkers: ['container.googleapis.com/Cluster'],
    apiServices: ['container.googleapis.com'],
    permissions: 'Monitoring Viewer',
    gcpCost: 'Cloud Monitoring API reads; depends on GKE monitoring configuration',
    elasticCost: 'GKE metrics ingest',
    signals: ['metrics'],
  },
  {
    id: 'cloudrun',
    name: 'Cloud Run',
    mode: 'optional',
    assetMarkers: ['run.googleapis.com/Service'],
    apiServices: ['run.googleapis.com'],
    permissions: 'Monitoring Viewer',
    gcpCost: 'Cloud Monitoring API reads',
    elasticCost: 'Cloud Run metrics ingest',
    signals: ['metrics'],
  },
  {
    id: 'cloudsql',
    name: 'Cloud SQL',
    mode: 'optional',
    assetMarkers: ['sqladmin.googleapis.com/Instance'],
    apiServices: ['sqladmin.googleapis.com'],
    permissions: 'Monitoring Viewer',
    gcpCost: 'Cloud Monitoring API reads',
    elasticCost: 'Cloud SQL metrics ingest',
    signals: ['metrics'],
  },
  {
    id: 'pubsub',
    name: 'Pub/Sub service metrics',
    mode: 'optional',
    assetMarkers: ['pubsub.googleapis.com/Topic', 'pubsub.googleapis.com/Subscription'],
    apiServices: ['pubsub.googleapis.com'],
    permissions: 'Monitoring Viewer',
    gcpCost: 'Cloud Monitoring API reads',
    elasticCost: 'Pub/Sub metrics ingest',
    signals: ['metrics'],
  },
  {
    id: 'firestore',
    name: 'Firestore',
    mode: 'optional',
    assetMarkers: ['firestore.googleapis.com/Database'],
    apiServices: ['firestore.googleapis.com'],
    permissions: 'Monitoring Viewer',
    gcpCost: 'Cloud Monitoring API reads',
    elasticCost: 'Firestore metrics ingest',
    signals: ['metrics'],
  },
  {
    id: 'dataproc',
    name: 'Dataproc',
    mode: 'optional',
    assetMarkers: ['dataproc.googleapis.com/Cluster'],
    apiServices: ['dataproc.googleapis.com'],
    permissions: 'Monitoring Viewer',
    gcpCost: 'Cloud Monitoring API reads',
    elasticCost: 'Dataproc metrics ingest',
    signals: ['metrics'],
  },
  {
    id: 'redis',
    name: 'Memorystore for Redis',
    mode: 'optional',
    assetMarkers: ['redis.googleapis.com/Instance'],
    apiServices: ['redis.googleapis.com'],
    permissions: 'Monitoring Viewer',
    gcpCost: 'Cloud Monitoring API reads',
    elasticCost: 'Redis metrics ingest',
    signals: ['metrics'],
  },
  {
    id: 'billing',
    name: 'Cloud Billing export',
    mode: 'optional',
    assetMarkers: ['bigquery.googleapis.com/Dataset'],
    apiServices: ['cloudbilling.googleapis.com', 'bigquery.googleapis.com'],
    permissions: 'Monitoring Viewer and access to the configured BigQuery billing export dataset',
    gcpCost: 'BigQuery billing export storage/query and Cloud Monitoring API reads',
    elasticCost: 'Billing metrics ingest',
    signals: ['metrics', 'cost'],
  },
];

type Manifest = {
  approved_projects: string[];
  resources: Array<{
    kind?: string;
    asset_type?: string;
    name?: string;
  }>;
};

export function recommendGcpIntegrations(
  manifest: Manifest,
): GcpIntegrationRecommendation[] {
  const assetTypes = new Set(
    manifest.resources
      .map((resource) => resource.asset_type)
      .filter((value): value is string => Boolean(value)),
  );
  const enabledApis = new Set(
    manifest.resources
      .filter((resource) => resource.kind === 'enabled_service')
      .map((resource) => resource.name?.split('/').at(-1))
      .filter((value): value is string => Boolean(value)),
  );
  return definitions.map((definition) => {
    const discovered =
      definition.assetMarkers.some((marker) => assetTypes.has(marker)) ||
      definition.apiServices.some((service) => enabledApis.has(service));
    const recommended = definition.mode === 'core' || discovered;
    const requiresConfiguration = definition.id === 'billing';
    return {
      ...definition,
      discovered,
      recommended,
      selectedByDefault: recommended && !requiresConfiguration,
      requiresConfiguration,
      reason:
        definition.mode === 'core'
          ? 'Core PoC signal kept available across customer environments.'
          : requiresConfiguration && discovered
            ? 'Discovery found billing-related APIs. Select after entering the BigQuery billing export dataset.'
          : discovered
            ? 'Discovery found this service or its enabled API.'
            : 'Not selected by default because discovery found no matching service.',
    };
  });
}

export function findUnmappedGcpServices(manifest: Manifest): string[] {
  const knownApis = new Set(
    definitions.flatMap((definition) => definition.apiServices),
  );
  const platformApis = new Set([
    'cloudasset.googleapis.com',
    'cloudresourcemanager.googleapis.com',
    'iam.googleapis.com',
    'logging.googleapis.com',
    'monitoring.googleapis.com',
    'serviceusage.googleapis.com',
  ]);
  return [
    ...new Set(
      manifest.resources
        .filter((resource) => resource.kind === 'enabled_service')
        .map((resource) => resource.name?.split('/').at(-1))
        .filter((service): service is string => Boolean(service))
        .filter(
          (service) =>
            !knownApis.has(service) && !platformApis.has(service),
        ),
    ),
  ]
    .sort()
    .slice(0, 50);
}

export async function readGcpManifestWithHash(filePath: string): Promise<{
  manifest: Manifest;
  manifestHash: string;
}> {
  const encoded = await fs.readFile(filePath);
  const manifest = JSON.parse(encoded.toString('utf8')) as Manifest;
  return {
    manifest,
    manifestHash: createHash('sha256').update(encoded).digest('hex'),
  };
}
