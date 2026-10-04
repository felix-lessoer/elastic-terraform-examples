import { parse } from 'dotenv';
import { promises as fs } from 'node:fs';
import { z } from 'zod';
import type { CredentialStatus } from './cloud-provider.js';
import { writeOwnerOnly } from './local-files.js';

const credentialSchema = z
  .object({
    elasticCloudApiKey: z.string().max(16_384).optional().default(''),
    applicationCredentialsPath: z.string().max(4096).optional().default(''),
    impersonateServiceAccount: z
      .string()
      .email()
      .endsWith('.gserviceaccount.com')
      .optional()
      .or(z.literal(''))
      .default(''),
  })
  .strict()
  .superRefine((value, context) => {
    for (const [key, item] of Object.entries(value)) {
      if (/[\u0000-\u001f\u007f]/.test(item)) {
        context.addIssue({
          code: 'custom',
          path: [key],
          message: 'Credential fields cannot contain control characters',
        });
      }
    }
  });

type StoredCredentials = Partial<
  Record<
    'EC_API_KEY' | 'GOOGLE_APPLICATION_CREDENTIALS' | 'GCP_IMPERSONATE_SERVICE_ACCOUNT',
    string
  >
>;

async function readStored(filePath: string): Promise<StoredCredentials> {
  try {
    return parse(await fs.readFile(filePath, 'utf8')) as StoredCredentials;
  } catch (error) {
    if (error instanceof Error && 'code' in error && error.code === 'ENOENT') {
      return {};
    }
    throw error;
  }
}

export function credentialStatus(
  stored: StoredCredentials,
  environment: NodeJS.ProcessEnv,
): CredentialStatus {
  const impersonation = Boolean(
    stored.GCP_IMPERSONATE_SERVICE_ACCOUNT ||
      environment.GCP_IMPERSONATE_SERVICE_ACCOUNT,
  );
  const adc = Boolean(
    stored.GOOGLE_APPLICATION_CREDENTIALS ||
      environment.GOOGLE_APPLICATION_CREDENTIALS ||
      environment.GOOGLE_GHA_CREDS_PATH,
  );
  return {
    elasticConfigured: Boolean(stored.EC_API_KEY || environment.EC_API_KEY),
    cloudConfigured: impersonation || adc || Boolean(environment.CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE),
    method: impersonation
      ? 'impersonation'
      : adc
        ? 'application-default'
        : environment.CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE
          ? 'environment'
          : 'none',
  };
}

export async function saveCredentials(
  filePath: string,
  input: unknown,
  environment: NodeJS.ProcessEnv = process.env,
): Promise<CredentialStatus> {
  const parsed = credentialSchema.parse(input);
  const previous = await readStored(filePath);
  const next: StoredCredentials = { ...previous };
  if (parsed.elasticCloudApiKey) next.EC_API_KEY = parsed.elasticCloudApiKey;
  if (parsed.applicationCredentialsPath) {
    next.GOOGLE_APPLICATION_CREDENTIALS = parsed.applicationCredentialsPath;
  }
  if (parsed.impersonateServiceAccount) {
    next.GCP_IMPERSONATE_SERVICE_ACCOUNT = parsed.impersonateServiceAccount;
  }
  if (!next.EC_API_KEY && !environment.EC_API_KEY) {
    throw new Error('Enter an Elastic Cloud API key');
  }
  if (
    !next.GOOGLE_APPLICATION_CREDENTIALS &&
    !next.GCP_IMPERSONATE_SERVICE_ACCOUNT &&
    !environment.GOOGLE_APPLICATION_CREDENTIALS &&
    !environment.GOOGLE_GHA_CREDS_PATH &&
    !environment.CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE
  ) {
    throw new Error('Configure application-default credentials or impersonation');
  }
  const contents = [
    '# Local-only Cloud PoC credentials. Never commit this file.',
    ...Object.entries(next).map(([key, value]) => `${key}=${JSON.stringify(value)}`),
    '',
  ].join('\n');
  await writeOwnerOnly(filePath, contents);
  Object.assign(environment, next);
  return credentialStatus(next, environment);
}

export async function readCredentialStatus(
  filePath: string,
  environment: NodeJS.ProcessEnv = process.env,
): Promise<CredentialStatus> {
  return credentialStatus(await readStored(filePath), environment);
}
