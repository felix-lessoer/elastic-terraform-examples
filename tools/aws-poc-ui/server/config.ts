import { promises as fs } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { z } from 'zod';

const serverDirectory = path.dirname(fileURLToPath(import.meta.url));

export const repoRoot = path.resolve(
  process.env.AWS_POC_REPO_ROOT ?? path.join(serverDirectory, '../../..'),
);

export const terraformDirectory = path.resolve(
  process.env.AWS_POC_TERRAFORM_DIR ?? path.join(repoRoot, 'examples/aws'),
);

if (
  terraformDirectory !== repoRoot &&
  !terraformDirectory.startsWith(`${repoRoot}${path.sep}`)
) {
  throw new Error('AWS_POC_TERRAFORM_DIR must be inside the repository');
}

export const generatedVariablesPath = path.join(
  terraformDirectory,
  'aws-poc-ui.auto.tfvars.json',
);

const tagValue = z.string().trim().min(1).max(256);

export const deploymentConfigSchema = z.object({
  elastic_project_name: z.string().trim().min(1).max(100),
  elastic_region: z.string().trim().regex(/^[a-z]{2,}-[a-z]+-[a-z]+-\d+$/),
  aws_region: z.string().trim().regex(/^[a-z]{2}(?:-gov)?-[a-z]+-\d+$/),
  elastic_agent_instance_type: z.string().trim().regex(/^[a-z0-9][a-z0-9.]*$/),
  existing_cloudtrail_bucket_name: z
    .string()
    .trim()
    .max(63)
    .refine(
      (value) =>
        value === '' ||
        /^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$/.test(value),
      'Enter a valid S3 bucket name',
    ),
  company_tags: z.record(
    z.string().trim().regex(/^[A-Za-z0-9_.:/=+\-@]{1,128}$/),
    tagValue,
  ),
  required_tag_keys: z.array(z.string().trim().min(1).max(128)).max(50),
});

export type DeploymentConfig = z.infer<typeof deploymentConfigSchema>;

export const defaultDeploymentConfig: DeploymentConfig = {
  elastic_project_name: 'AWS Observability',
  elastic_region: 'aws-eu-west-1',
  aws_region: 'eu-west-1',
  elastic_agent_instance_type: 't3.medium',
  existing_cloudtrail_bucket_name: '',
  company_tags: {
    division: 'field',
    org: 'sa',
    'keep-until': '2026-10-01',
    team: 'change-me',
    project: 'aws-observability',
    environment: 'poc',
  },
  required_tag_keys: [
    'division',
    'org',
    'keep-until',
    'team',
    'project',
    'environment',
  ],
};

export async function readDeploymentConfig(): Promise<{
  config: DeploymentConfig;
  saved: boolean;
}> {
  try {
    const contents = await fs.readFile(generatedVariablesPath, 'utf8');
    return {
      config: deploymentConfigSchema.parse(JSON.parse(contents)),
      saved: true,
    };
  } catch (error) {
    if (
      error instanceof Error &&
      'code' in error &&
      error.code === 'ENOENT'
    ) {
      return { config: defaultDeploymentConfig, saved: false };
    }
    throw error;
  }
}

export async function writeDeploymentConfig(
  input: unknown,
): Promise<DeploymentConfig> {
  const config = deploymentConfigSchema.parse(input);
  await fs.writeFile(
    generatedVariablesPath,
    `${JSON.stringify(config, null, 2)}\n`,
    { mode: 0o600 },
  );
  return config;
}
