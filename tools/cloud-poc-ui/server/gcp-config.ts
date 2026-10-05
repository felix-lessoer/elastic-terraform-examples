import { promises as fs } from 'node:fs';
import { z } from 'zod';
import {
  gcpCoreServiceIds,
  gcpServiceIdSchema,
} from './gcp-integrations.js';
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
    selectedServiceIds: z.array(gcpServiceIdSchema).max(50).default([]),
    billingDatasetId: z
      .string()
      .trim()
      .max(256)
      .regex(
        /^[A-Za-z0-9_.:-]*$/,
        'Enter a valid BigQuery billing dataset ID',
      )
      .default(''),
    selectionProjectId: z
      .string()
      .regex(/^[a-z][a-z0-9-]{4,61}[a-z0-9]$/)
      .optional(),
    selectionManifestHash: z
      .string()
      .regex(/^[a-f0-9]{64}$/)
      .optional(),
  })
  .strict()
  .superRefine((config, context) => {
    if (config.elasticLabelsRequired) {
      for (const key of config.requiredLabelKeys) {
        if (!config.companyLabels[key]) {
          context.addIssue({
            code: 'custom',
            path: ['companyLabels', key],
            message: `Enter the required label ${key}`,
          });
        }
      }
    }
    const hasSelectionBinding =
      config.selectionProjectId !== undefined ||
      config.selectionManifestHash !== undefined;
    if (
      hasSelectionBinding &&
      (!config.selectionProjectId || !config.selectionManifestHash)
    ) {
      context.addIssue({
        code: 'custom',
        path: ['selectionManifestHash'],
        message: 'Integration selection requires a project and manifest hash',
      });
    }
    if (
      new Set(config.selectedServiceIds).size !==
      config.selectedServiceIds.length
    ) {
      context.addIssue({
        code: 'custom',
        path: ['selectedServiceIds'],
        message: 'Integration selection contains duplicate services',
      });
    }
    if (
      config.selectedServiceIds.includes('billing') &&
      !config.billingDatasetId
    ) {
      context.addIssue({
        code: 'custom',
        path: ['billingDatasetId'],
        message: 'Billing metrics require a BigQuery billing dataset ID',
      });
    }
    if (
      config.selectionManifestHash &&
      gcpCoreServiceIds.some(
        (service) => !config.selectedServiceIds.includes(service),
      )
    ) {
      context.addIssue({
        code: 'custom',
        path: ['selectedServiceIds'],
        message: 'The core customer PoC integrations must remain selected',
      });
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
  selectedServiceIds: [],
  billingDatasetId: '',
};

export async function readGcpDeploymentConfig(
  filePath: string,
): Promise<{
  config: GcpDeploymentConfig;
  saved: boolean;
  updatedAt?: string;
}> {
  const value = await readJson<unknown | undefined>(filePath, undefined);
  if (value === undefined) {
    return { config: defaultGcpDeploymentConfig, saved: false };
  }
  const metadata = await fs.stat(filePath);
  return {
    config: gcpDeploymentConfigSchema.parse(value),
    saved: true,
    updatedAt: metadata.mtime.toISOString(),
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
