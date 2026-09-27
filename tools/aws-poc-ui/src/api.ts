export interface DeploymentConfig {
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

export interface Bootstrap {
  csrfToken: string;
  repoRoot: string;
  terraformDirectory: string;
  status: DeploymentStatus;
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
    return fetch('/api/config').then(parse);
  },
  async status(): Promise<DeploymentStatus> {
    return fetch('/api/status').then(parse);
  },
  async runs(): Promise<RunRecord[]> {
    return fetch('/api/runs').then(parse);
  },
  saveConfig(config: DeploymentConfig) {
    return mutate<{ config: DeploymentConfig; saved: boolean }>(
      '/api/config',
      'PUT',
      config,
    );
  },
  startStep(step: 'preflight' | 'init' | 'plan' | 'apply') {
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
