import { promises as fs } from 'node:fs';
import path from 'node:path';
import { z } from 'zod';
import type {
  CloudProvider,
  CredentialStatus,
  GuidedOperation,
  OperationRequest,
  ProviderContext,
} from '../cloud-provider.js';
import type { CommandRunner } from '../commands.js';
import type { GcpDeploymentConfig } from '../gcp-config.js';
import { writeOwnerOnly } from '../local-files.js';
import { summarizeTerraformPlan } from '../terraform-plan.js';
import {
  candidatesFromResources,
  type VisibilityCandidate,
} from '../visibility.js';

const projectIdSchema = z
  .string()
  .regex(/^[a-z][a-z0-9-]{4,61}[a-z0-9]$/);
const workflowIds = new Set([
  'gcp-cockpit-assets',
  'gcp-cockpit-coverage',
  'gcp-cockpit-host-recommendations',
  'gcp-cockpit-gke-recommendations',
  'gcp-cockpit-cloudrun-recommendations',
  'gcp-cockpit-cloudsql-recommendations',
]);
const planName = '.cloud-poc-gcp.tfplan';

export class GcpProvider implements CloudProvider {
  readonly slug = 'gcp' as const;
  readonly displayName = 'Google Cloud';

  constructor(
    readonly terraformDirectory: string,
    private readonly artifactDirectory: string,
    private readonly runner: CommandRunner,
    private readonly credentials: () => Promise<CredentialStatus>,
    private readonly configuration: () => Promise<GcpDeploymentConfig>,
    private readonly environment: NodeJS.ProcessEnv = process.env,
  ) {}

  credentialStatus(): Promise<CredentialStatus> {
    return this.credentials();
  }

  async execute(
    operation: GuidedOperation,
    request: OperationRequest,
    context: ProviderContext,
  ): Promise<unknown> {
    const projectId = projectIdSchema.parse(request.projectId);
    switch (operation) {
      case 'preflight':
        return this.preflight(projectId, context);
      case 'terraform-init':
        return this.command('terraform.init', {}, context);
      case 'terraform-plan':
        return this.plan(projectId, context);
      case 'terraform-apply':
        if (request.confirmation !== 'APPLY') {
          throw new Error('Applying the saved plan requires confirmation APPLY');
        }
        return this.command('terraform.apply', { plan: planName }, context);
      case 'discovery':
        return this.discover(projectId, context);
      case 'analysis':
        return this.analyze(projectId, context);
      case 'workflows':
        return this.runWorkflows(request.workflowIds ?? [], context);
      case 'final-links':
        return {
          cockpit: this.safeCockpitUrl(),
          cloudConsole: `https://console.cloud.google.com/home/dashboard?project=${projectId}`,
        };
    }
  }

  private async preflight(projectId: string, context: ProviderContext) {
    await context.progress({
      stage: 'credentials',
      message: 'Checking local credentials',
      percent: 15,
    });
    const credentials = await this.credentialStatus();
    if (!credentials.elasticConfigured || !credentials.cloudConfigured) {
      throw new Error('Save Elastic and Google Cloud credentials before preflight');
    }
    await context.progress({
      stage: 'tools',
      message: 'Checking Terraform and Google Cloud CLI',
      percent: 35,
    });
    const terraform = await this.command('terraform.version', {}, context);
    const gcloud = await this.command('gcloud.version', {}, context);
    await context.progress({
      stage: 'identity',
      message: `Validating access to ${projectId}`,
      percent: 70,
    });
    const identity = await this.command(
      'gcp.identity',
      { projectId },
      context,
    );
    const terraformVersion = JSON.parse(terraform.stdout) as {
      terraform_version?: string;
    };
    const gcloudVersion = JSON.parse(gcloud.stdout) as Record<string, string>;
    return {
      credentials,
      tools: {
        terraform: terraformVersion.terraform_version ?? 'available',
        gcloud:
          gcloudVersion['Google Cloud SDK'] ??
          gcloudVersion.GoogleCloudSDK ??
          'available',
      },
      identity: JSON.parse(identity.stdout),
    };
  }

  private async discover(projectId: string, context: ProviderContext) {
    await context.progress({
      stage: 'inventory',
      message: `Reading Cloud Asset Inventory for ${projectId}`,
      percent: 10,
    });
    const manifestPath = path.resolve(
      this.artifactDirectory,
      'gcp-manifest.json',
    );
    await fs.mkdir(this.artifactDirectory, { recursive: true, mode: 0o700 });
    const result = await this.command(
      'gcp.discover',
      { projectId, manifestPath },
      context,
    );
    const output = JSON.parse(result.stdout) as {
      manifest_sha256: string;
      summary: {
        complete: boolean;
        resources: number;
        statuses: Record<string, number>;
      };
    };
    if (!/^[a-f0-9]{64}$/.test(output.manifest_sha256)) {
      throw new Error('Discovery returned an invalid manifest hash');
    }
    await context.progress({
      stage: 'validating',
      message: 'Validating and hashing the local manifest',
      percent: 90,
    });
    return {
      manifestVersion: '1.0',
      manifestHash: output.manifest_sha256,
      resourceCount: output.summary.resources,
      partial: !output.summary.complete,
      warnings: !output.summary.complete
        ? [`Discovery returned partial results: ${JSON.stringify(output.summary.statuses)}`]
        : [],
    };
  }

  private async analyze(projectId: string, context: ProviderContext) {
    await context.progress({
      stage: 'analysis',
      message: 'Building deterministic visibility candidates',
      percent: 30,
    });
    const manifest = JSON.parse(
      await fs.readFile(path.join(this.artifactDirectory, 'gcp-manifest.json'), 'utf8'),
    ) as {
      approved_projects: string[];
      resources: Array<{
        resource_id?: string;
        display_name?: string;
        asset_type?: string;
        state?: string;
      }>;
    };
    if (!manifest.approved_projects.includes(projectId)) {
      throw new Error('Run discovery for the selected project before analysis');
    }
    const candidates: VisibilityCandidate[] = candidatesFromResources(
      manifest.resources
        .filter((resource) => Boolean(resource.asset_type))
        .map((resource) => ({
          id: resource.resource_id ?? '',
          name:
            resource.display_name ??
            resource.resource_id ??
            'unnamed',
          type: resource.asset_type ?? 'unknown',
          state: resource.state ?? 'unknown',
        })),
    );
    const analysis = {
      schemaVersion: '1.0',
      projectId,
      missingTelemetryMeans: 'unknown',
      candidates,
    };
    await writeOwnerOnly(
      path.join(this.artifactDirectory, 'gcp-analysis.json'),
      `${JSON.stringify(analysis, null, 2)}\n`,
    );
    return analysis;
  }

  private async runWorkflows(ids: string[], context: ProviderContext) {
    const selected = ids.length === 0 ? [...workflowIds] : ids;
    if (selected.some((id) => !workflowIds.has(id))) {
      throw new Error('Unknown GCP workflow ID');
    }
    await context.progress({
      stage: 'workflows',
      message: `Prepared ${selected.length} allow-listed GCP workflows`,
      percent: 80,
    });
    return {
      workflowIds: selected,
      execution: 'provider-contract',
      note: 'A deployment integration supplies the authenticated Elastic workflow executor.',
    };
  }

  private async plan(projectId: string, context: ProviderContext) {
    const configuration = await this.configuration();
    const companyLabels = configuration.elasticLabelsRequired
      ? configuration.companyLabels
      : {
          owner: 'elastic-poc-ui',
          environment: 'poc',
          project: projectId,
        };
    const requiredLabelKeys = configuration.elasticLabelsRequired
      ? configuration.requiredLabelKeys
      : [];
    await this.command(
      'terraform.plan',
      {
        plan: planName,
        projectId,
        companyLabels: JSON.stringify(companyLabels),
        requiredLabelKeys: JSON.stringify(requiredLabelKeys),
        elasticLabelsRequired: String(
          configuration.elasticLabelsRequired,
        ),
      },
      context,
    );
    await context.progress({
      stage: 'validating',
      message: 'Rendering readable saved-plan actions',
      percent: 90,
    });
    const shown = await this.command(
      'terraform.show',
      { plan: planName },
      context,
    );
    return {
      ...summarizeTerraformPlan(JSON.parse(shown.stdout)),
      labels: {
        elasticInternalRequired:
          configuration.elasticLabelsRequired,
        keys: Object.keys(companyLabels).sort(),
        requiredKeys: [...requiredLabelKeys].sort(),
      },
    };
  }

  private async command(
    id: Parameters<CommandRunner['run']>[0],
    values: Record<string, string>,
    context: ProviderContext,
  ) {
    const result = await this.runner.run(id, values, {
      cwd: this.terraformDirectory,
      write: context.write,
    });
    if (result.exitCode !== 0) {
      throw new Error(result.stderr || `${id} failed`);
    }
    return result;
  }

  private safeCockpitUrl(): string | undefined {
    const value = this.environment.GCP_POC_COCKPIT_URL;
    if (!value) return undefined;
    try {
      const url = new URL(value);
      return url.protocol === 'https:' ? url.toString() : undefined;
    } catch {
      return undefined;
    }
  }
}
