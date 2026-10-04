import { z } from 'zod';
import { readJson, writeOwnerOnly } from './local-files.js';

const labelKey = z
  .string()
  .trim()
  .regex(/^[a-z][a-z0-9_-]{0,62}$/, 'Enter a valid GCP label key');
const labelValue = z
  .string()
  .trim()
  .min(1)
  .max(63)
  .regex(/^[a-z0-9_-]+$/, 'Use lowercase GCP label characters');

export const gcpDeploymentConfigSchema = z
  .object({
    elasticLabelsRequired: z.boolean().default(false),
    companyLabels: z.record(labelKey, labelValue),
    requiredLabelKeys: z.array(labelKey).max(50),
  })
  .strict()
  .superRefine((config, context) => {
    if (!config.elasticLabelsRequired) return;
    for (const key of config.requiredLabelKeys) {
      if (!config.companyLabels[key]) {
        context.addIssue({
          code: 'custom',
          path: ['companyLabels', key],
          message: `Enter the required label ${key}`,
        });
      }
    }
  });

export type GcpDeploymentConfig = z.infer<
  typeof gcpDeploymentConfigSchema
>;

export const defaultGcpDeploymentConfig: GcpDeploymentConfig = {
  elasticLabelsRequired: false,
  companyLabels: {
    division: 'field',
    org: 'sa',
    'keep-until': '2026-10-31',
    team: 'change-me',
    project: 'gcp-observability',
    environment: 'poc',
  },
  requiredLabelKeys: [
    'division',
    'org',
    'keep-until',
    'team',
    'project',
    'environment',
  ],
};

export async function readGcpDeploymentConfig(
  filePath: string,
): Promise<{ config: GcpDeploymentConfig; saved: boolean }> {
  const value = await readJson<unknown | undefined>(filePath, undefined);
  if (value === undefined) {
    return { config: defaultGcpDeploymentConfig, saved: false };
  }
  return {
    config: gcpDeploymentConfigSchema.parse(value),
    saved: true,
  };
}

export async function writeGcpDeploymentConfig(
  filePath: string,
  input: unknown,
): Promise<GcpDeploymentConfig> {
  const config = gcpDeploymentConfigSchema.parse(input);
  await writeOwnerOnly(filePath, `${JSON.stringify(config, null, 2)}\n`);
  return config;
}
