import type { LogWriter } from './run-manager.js';
import { readTerraformOutputs } from './terraform.js';

interface ElasticConnection {
  kibanaUrl: string;
  username: string;
  password: string;
  workflowIds: string[];
}

function stringValue(
  outputs: Awaited<ReturnType<typeof readTerraformOutputs>>,
  name: string,
): string {
  const value = outputs[name]?.value;
  if (typeof value !== 'string' || value.length === 0) {
    throw new Error(`Terraform output ${name} is unavailable`);
  }
  return value;
}

async function connection(): Promise<ElasticConnection> {
  const outputs = await readTerraformOutputs();
  const workflowIds = outputs.workflow_ids?.value;
  return {
    kibanaUrl: stringValue(outputs, 'kibana_url').replace(/\/+$/, ''),
    username: stringValue(outputs, 'username'),
    password: stringValue(outputs, 'password'),
    workflowIds: Array.isArray(workflowIds)
      ? workflowIds.filter((value): value is string => typeof value === 'string')
      : [],
  };
}

export async function runElasticWorkflow(
  workflowId: string,
  write: LogWriter,
): Promise<{ workflowExecutionId: string }> {
  const details = await connection();
  if (!details.workflowIds.includes(workflowId)) {
    throw new Error(`Workflow ${workflowId} is not deployed by this stack`);
  }

  write(`Triggering Elastic workflow ${workflowId}`);
  const response = await fetch(
    `${details.kibanaUrl}/api/workflows/workflow/${encodeURIComponent(workflowId)}/run`,
    {
      method: 'POST',
      headers: {
        Authorization: `Basic ${Buffer.from(
          `${details.username}:${details.password}`,
        ).toString('base64')}`,
        'Content-Type': 'application/json',
        'kbn-xsrf': 'aws-poc-ui',
      },
      body: JSON.stringify({ inputs: {}, metadata: { source: 'aws-poc-ui' } }),
      signal: AbortSignal.timeout(60_000),
    },
  );

  const body = (await response.json().catch(() => ({}))) as {
    workflowExecutionId?: string;
    message?: string;
  };
  if (!response.ok || !body.workflowExecutionId) {
    throw new Error(
      body.message ||
        `Workflow request failed with HTTP ${response.status}`,
    );
  }
  write(`Workflow execution: ${body.workflowExecutionId}`);
  return { workflowExecutionId: body.workflowExecutionId };
}
