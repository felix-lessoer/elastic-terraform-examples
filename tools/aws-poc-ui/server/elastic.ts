import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { repoRoot } from './config.js';
import type { LogWriter } from './run-manager.js';
import { executeCommand } from './run-manager.js';
import { readTerraformOutputs } from './terraform.js';

interface ElasticConnection {
  elasticsearchUrl: string;
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
    elasticsearchUrl:
      typeof outputs.elasticsearch_url?.value === 'string'
        ? outputs.elasticsearch_url.value.replace(/\/+$/, '')
        : stringValue(outputs, 'kibana_url')
            .replace('.kb.', '.es.')
            .replace(/\/+$/, ''),
    username: stringValue(outputs, 'username'),
    password: stringValue(outputs, 'password'),
    workflowIds: Array.isArray(workflowIds)
      ? workflowIds.filter((value): value is string => typeof value === 'string')
      : [],
  };
}

async function runInsightScript(
  script: string,
  args: string[],
  details: ElasticConnection,
  write: LogWriter,
): Promise<void> {
  const result = await executeCommand('python3', [script, ...args], {
    cwd: repoRoot,
    write,
    env: {
      ...process.env,
      ELASTICSEARCH_PASSWORD: details.password,
    },
  });
  if (result.exitCode !== 0) {
    throw Object.assign(new Error(`${path.basename(script)} failed`), {
      exitCode: result.exitCode,
    });
  }
}

async function importCockpitDashboard(
  details: ElasticConnection,
  write: LogWriter,
): Promise<void> {
  const dashboard = await readFile(
    path.join(repoRoot, 'modules/cockpit-dashboard/cockpit-aws.ndjson'),
  );
  const form = new FormData();
  form.append(
    'file',
    new Blob([dashboard.toString('utf8')], {
      type: 'application/x-ndjson',
    }),
    'cockpit-aws.ndjson',
  );
  write('Updating cockpit visualizations to use stable snapshot indices');
  const response = await fetch(
    `${details.kibanaUrl}/api/saved_objects/_import?overwrite=true`,
    {
      method: 'POST',
      headers: {
        Authorization: `Basic ${Buffer.from(
          `${details.username}:${details.password}`,
        ).toString('base64')}`,
        'kbn-xsrf': 'aws-poc-ui',
      },
      body: form,
      signal: AbortSignal.timeout(120_000),
    },
  );
  const body = (await response.json().catch(() => ({}))) as {
    success?: boolean;
    message?: string;
  };
  if (!response.ok || body.success !== true) {
    throw new Error(
      body.message ||
        `Cockpit dashboard import failed with HTTP ${response.status}`,
    );
  }
}

export async function refreshElasticInsights(
  write: LogWriter,
): Promise<{ refreshed: string[] }> {
  const details = await connection();
  const scripts = path.join(repoRoot, 'modules/cockpit-dashboard/scripts');
  await importCockpitDashboard(details, write);
  write('Configuring the cockpit as the Elastic landing page');
  await runInsightScript(
    path.join(scripts, 'set_kibana_default_route.py'),
    [
      '--kibana-url',
      details.kibanaUrl,
      '--user',
      details.username,
      '--password',
      details.password,
      '--dashboard-id',
      '45f84000-d68b-4bb1-9df2-09223fba6b29',
    ],
    details,
    write,
  );
  write('Refreshing stable cockpit indices from available AWS telemetry');
  await runInsightScript(
    path.join(scripts, 'generate_aws_recommendations.py'),
    [
      '--es-url',
      details.elasticsearchUrl,
      '--user',
      details.username,
      '--password',
      details.password,
    ],
    details,
    write,
  );
  await runInsightScript(
    path.join(scripts, 'seed_aws_insight_indices.py'),
    [
      '--obs-es',
      details.elasticsearchUrl,
      '--sec-es',
      details.elasticsearchUrl,
      '--sec-kibana',
      details.kibanaUrl,
      '--obs-user',
      details.username,
      '--sec-user',
      details.username,
      '--obs-password',
      details.password,
      '--sec-password',
      details.password,
      '--manifest',
      path.join(repoRoot, 'tools/aws-poc-ui/.elastic-poc/manifest.json'),
    ],
    details,
    write,
  );
  if (details.workflowIds.includes('aws-cockpit-insight-engine-summary')) {
    write('Starting the Agent Builder Insight Engine summary');
    await runElasticWorkflow('aws-cockpit-insight-engine-summary', write);
  }
  write('Cockpit Insight Engine snapshots refreshed');
  return {
    refreshed: [
      'aws-cockpit-recommendations',
      'aws-cockpit-insight-summary',
      'aws-cockpit-security-kpi',
      'aws-cockpit-coverage',
      'aws-cockpit-assets',
      'aws-cockpit-health',
      'aws-cockpit-events',
    ],
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
