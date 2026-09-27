export interface DeploymentConfig {
  deployment_creator_mode: true;
  elastic_tags_required: boolean;
  elastic_project_name: string;
  elastic_region: string;
  aws_region: string;
  elastic_agent_instance_type: string;
  existing_cloudtrail_bucket_name: string;
  company_tags: Record<string, string>;
  required_tag_keys: string[];
}

export interface DeploymentStatus {
  configured: boolean;
  initialized: boolean;
  planned: boolean;
  deployed: boolean;
  outputs: {
    aws_account_id?: string;
    cockpit_dashboard_url?: string;
    kibana_url?: string;
    managed_integration_names?: string[];
    project_id?: string;
    regional_security_agent_regions?: string[];
    workflow_ids?: string[];
  };
}

export type PlanAction = 'create' | 'update' | 'replace' | 'delete' | 'read';

export interface PlannedResource {
  address: string;
  module: string;
  type: string;
  name: string;
  action: PlanAction;
}

export interface PlanSummary {
  generatedAt?: string;
  resources: PlannedResource[];
  counts: Record<PlanAction, number>;
}

export interface CredentialsStatus {
  path: string;
  elasticCloudApiKey: {
    configured: boolean;
    saved: boolean;
  };
  aws: {
    configured: boolean;
    saved: boolean;
    mode: 'profile' | 'accessKeys' | 'environment' | 'none';
    hasSessionToken: boolean;
  };
}

export interface CredentialsInput {
  elasticCloudApiKey: string;
  awsMode: 'profile' | 'accessKeys';
  awsProfile: string;
  awsAccessKeyId: string;
  awsSecretAccessKey: string;
  awsSessionToken: string;
}

export interface Bootstrap {
  csrfToken: string;
  repoRoot: string;
  terraformDirectory: string;
  status: DeploymentStatus;
  credentials: CredentialsStatus;
}

export interface PreflightCheck {
  id: string;
  label: string;
  status: 'passed' | 'failed' | 'warning';
  detail: string;
}

export interface RunRecord {
  id: string;
  step: string;
  title: string;
  status: 'running' | 'succeeded' | 'failed';
  startedAt: string;
  finishedAt?: string;
  exitCode?: number;
  logs: string[];
  result?: {
    checks?: PreflightCheck[];
    passed?: boolean;
    workflowExecutionId?: string;
  };
}

export interface BrownfieldArtifactStatus {
  modifiedAt: string;
  summary: {
    resources?: number;
    edges?: number;
    service_resources?: number;
    service_candidates?: number;
    dependencies?: number;
    findings?: number;
    proposals?: number;
    errors?: number;
    required_coverage?: {
      numerator: number;
      denominator: number;
      percentage: number | null;
    };
    findings_by_severity?: Record<string, number>;
  };
  limitations: string[];
}

export interface BrownfieldStatus {
  manifest: BrownfieldArtifactStatus | null;
  analysis: BrownfieldArtifactStatus | null;
}

export interface VisibilityProposal {
  id: string;
  resource_arn: string;
  resource_name: string;
  resource_type: string;
  signal: string;
  priority: number;
  change_summary: string;
  prerequisites: string[];
  cost_dimensions: string[];
  validation: string[];
  rollback: string[];
}

export interface VisibilityOption {
  id: string;
  title: string;
  signal: string;
  resourceType: string;
  affectedResources: number;
  recommendedCanary: VisibilityProposal;
}

export interface VisibilityExpansionStatus {
  options: VisibilityOption[];
  selectedProposalIds: string[];
}

let bootstrapPromise: Promise<Bootstrap> | undefined;

async function parse<T>(response: Response): Promise<T> {
  const body = (await response.json().catch(() => ({}))) as T & {
    message?: string;
  };
  if (!response.ok) {
    throw new Error(body.message || `Request failed with HTTP ${response.status}`);
  }
  return body;
}

export function getBootstrap(): Promise<Bootstrap> {
  bootstrapPromise ??= fetch('/api/bootstrap', { cache: 'no-store' }).then(
    parse<Bootstrap>,
  );
  return bootstrapPromise;
}

function query<T>(path: string): Promise<T> {
  return fetch(path, { cache: 'no-store' }).then(parse<T>);
}

async function mutate<T>(
  path: string,
  method: 'POST' | 'PUT',
  body: unknown,
): Promise<T> {
  const bootstrap = await getBootstrap();
  return fetch(path, {
    method,
    headers: {
      'Content-Type': 'application/json',
      'x-aws-poc-csrf': bootstrap.csrfToken,
    },
    body: JSON.stringify(body),
  }).then(parse<T>);
}

export const api = {
  bootstrap: getBootstrap,
  async config(): Promise<{ config: DeploymentConfig; saved: boolean }> {
    return query<{ config: DeploymentConfig; saved: boolean }>('/api/config');
  },
  async credentials(): Promise<CredentialsStatus> {
    return query<CredentialsStatus>('/api/credentials');
  },
  async status(): Promise<DeploymentStatus> {
    return query<DeploymentStatus>('/api/status');
  },
  async plan(): Promise<PlanSummary | null> {
    return query<PlanSummary | null>('/api/plan');
  },
  async brownfield(): Promise<BrownfieldStatus> {
    return query<BrownfieldStatus>('/api/brownfield');
  },
  async visibilityExpansions(): Promise<VisibilityExpansionStatus> {
    return query<VisibilityExpansionStatus>('/api/visibility-expansions');
  },
  async runs(): Promise<RunRecord[]> {
    return query<RunRecord[]>('/api/runs');
  },
  saveConfig(config: DeploymentConfig) {
    return mutate<{ config: DeploymentConfig; saved: boolean }>(
      '/api/config',
      'PUT',
      config,
    );
  },
  saveCredentials(credentials: CredentialsInput) {
    return mutate<CredentialsStatus>(
      '/api/credentials',
      'PUT',
      credentials,
    );
  },
  saveVisibilityExpansions(selectedProposalIds: string[]) {
    return mutate<VisibilityExpansionStatus>(
      '/api/visibility-expansions',
      'PUT',
      { selectedProposalIds },
    );
  },
  startStep(
    step: 'preflight' | 'init' | 'plan' | 'apply' | 'discovery' | 'analysis',
  ) {
    return mutate<RunRecord>(
      `/api/runs/${step}`,
      'POST',
      step === 'apply' ? { confirmation: 'APPLY' } : {},
    );
  },
  runWorkflow(workflowId: string) {
    return mutate<RunRecord>(
      `/api/workflows/${encodeURIComponent(workflowId)}/run`,
      'POST',
      {},
    );
  },
  runAllWorkflows() {
    return mutate<RunRecord>('/api/workflows/run-all', 'POST', {});
  },
  subscribe(runId: string, onRun: (run: RunRecord) => void): () => void {
    const events = new EventSource(`/api/runs/${runId}/events`);
    events.onmessage = (event) => {
      onRun(JSON.parse(event.data) as RunRecord);
    };
    return () => events.close();
  },
};
