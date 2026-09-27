export interface DeploymentConfig {
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
  bootstrapPromise ??= fetch('/api/bootstrap').then(parse<Bootstrap>);
  return bootstrapPromise;
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
    return fetch('/api/config').then(
      parse<{ config: DeploymentConfig; saved: boolean }>,
    );
  },
  async credentials(): Promise<CredentialsStatus> {
    return fetch('/api/credentials').then(parse<CredentialsStatus>);
  },
  async status(): Promise<DeploymentStatus> {
    return fetch('/api/status').then(parse<DeploymentStatus>);
  },
  async brownfield(): Promise<BrownfieldStatus> {
    return fetch('/api/brownfield').then(parse<BrownfieldStatus>);
  },
  async runs(): Promise<RunRecord[]> {
    return fetch('/api/runs').then(parse<RunRecord[]>);
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
  subscribe(runId: string, onRun: (run: RunRecord) => void): () => void {
    const events = new EventSource(`/api/runs/${runId}/events`);
    events.onmessage = (event) => {
      onRun(JSON.parse(event.data) as RunRecord);
    };
    return () => events.close();
  },
};
