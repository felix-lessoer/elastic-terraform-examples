import { promises as fs } from 'node:fs';
import path from 'node:path';
import { parse, config as loadDotenv } from 'dotenv';
import { z } from 'zod';
import { repoRoot } from './config.js';

export const credentialsPath = path.join(
  repoRoot,
  'tools/aws-poc-ui/.env',
);

const managedKeys = [
  'EC_API_KEY',
  'AWS_PROFILE',
  'AWS_ACCESS_KEY_ID',
  'AWS_SECRET_ACCESS_KEY',
  'AWS_SESSION_TOKEN',
] as const;

type ManagedKey = (typeof managedKeys)[number];
type CredentialValues = Partial<Record<ManagedKey, string>>;

loadDotenv({ path: credentialsPath, override: false, quiet: true });

const optionalSecret = z
  .string()
  .max(16_384)
  .refine((value) => !/[\u0000-\u001f\u007f]/.test(value), {
    message: 'Credentials cannot contain control characters',
  })
  .optional()
  .default('');

export const credentialsInputSchema = z
  .object({
    elasticCloudApiKey: optionalSecret,
    awsMode: z.enum(['profile', 'accessKeys']),
    awsProfile: z
      .string()
      .max(128)
      .regex(/^[A-Za-z0-9_.@+\-]*$/, 'Enter a valid AWS profile name')
      .optional()
      .default(''),
    awsAccessKeyId: optionalSecret,
    awsSecretAccessKey: optionalSecret,
    awsSessionToken: optionalSecret,
  })
  .strict();

export type CredentialsInput = z.infer<typeof credentialsInputSchema>;

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

async function readCredentialFile(): Promise<CredentialValues> {
  try {
    const contents = await fs.readFile(credentialsPath, 'utf8');
    const parsed = parse(contents);
    return Object.fromEntries(
      managedKeys
        .filter((key) => typeof parsed[key] === 'string' && parsed[key] !== '')
        .map((key) => [key, parsed[key]]),
    ) as CredentialValues;
  } catch (error) {
    if (
      error instanceof Error &&
      'code' in error &&
      error.code === 'ENOENT'
    ) {
      return {};
    }
    throw error;
  }
}

function statusFrom(fileValues: CredentialValues): CredentialsStatus {
  const savedAccessKeys = Boolean(
    fileValues.AWS_ACCESS_KEY_ID && fileValues.AWS_SECRET_ACCESS_KEY,
  );
  const configuredAccessKeys = Boolean(
    process.env.AWS_ACCESS_KEY_ID && process.env.AWS_SECRET_ACCESS_KEY,
  );
  const savedProfile = Boolean(fileValues.AWS_PROFILE);
  const configuredProfile = Boolean(process.env.AWS_PROFILE);

  let mode: CredentialsStatus['aws']['mode'] = 'none';
  if (savedAccessKeys || configuredAccessKeys) mode = 'accessKeys';
  else if (savedProfile || configuredProfile) mode = 'profile';
  else if (
    process.env.AWS_WEB_IDENTITY_TOKEN_FILE ||
    process.env.AWS_CONTAINER_CREDENTIALS_RELATIVE_URI
  ) {
    mode = 'environment';
  }

  return {
    path: credentialsPath,
    elasticCloudApiKey: {
      configured: Boolean(process.env.EC_API_KEY),
      saved: Boolean(fileValues.EC_API_KEY),
    },
    aws: {
      configured:
        configuredAccessKeys ||
        configuredProfile ||
        mode === 'environment',
      saved: savedAccessKeys || savedProfile,
      mode,
      hasSessionToken: Boolean(process.env.AWS_SESSION_TOKEN),
    },
  };
}

export async function credentialsStatus(): Promise<CredentialsStatus> {
  return statusFrom(await readCredentialFile());
}

function serialize(values: CredentialValues): string {
  const lines = [
    '# Local credentials for the Elastic AWS PoC Guide.',
    '# Never commit this file.',
  ];
  for (const key of managedKeys) {
    const value = values[key];
    if (value) lines.push(`${key}=${JSON.stringify(value)}`);
  }
  return `${lines.join('\n')}\n`;
}

export async function saveCredentials(
  unknownInput: unknown,
): Promise<CredentialsStatus> {
  const input = credentialsInputSchema.parse(unknownInput);
  const previous = await readCredentialFile();
  const next: CredentialValues = { ...previous };

  if (input.elasticCloudApiKey) {
    next.EC_API_KEY = input.elasticCloudApiKey;
  }

  if (input.awsMode === 'profile') {
    delete next.AWS_ACCESS_KEY_ID;
    delete next.AWS_SECRET_ACCESS_KEY;
    delete next.AWS_SESSION_TOKEN;
    if (input.awsProfile) next.AWS_PROFILE = input.awsProfile;
    if (!next.AWS_PROFILE && !process.env.AWS_PROFILE) {
      throw new Error('Enter an AWS profile name');
    }
  } else {
    delete next.AWS_PROFILE;
    if (input.awsAccessKeyId) next.AWS_ACCESS_KEY_ID = input.awsAccessKeyId;
    if (input.awsSecretAccessKey) {
      next.AWS_SECRET_ACCESS_KEY = input.awsSecretAccessKey;
    }
    if (input.awsSessionToken) {
      next.AWS_SESSION_TOKEN = input.awsSessionToken;
    } else if (
      input.awsAccessKeyId ||
      input.awsSecretAccessKey
    ) {
      delete next.AWS_SESSION_TOKEN;
    }
    if (
      !(next.AWS_ACCESS_KEY_ID && next.AWS_SECRET_ACCESS_KEY) &&
      !(process.env.AWS_ACCESS_KEY_ID && process.env.AWS_SECRET_ACCESS_KEY)
    ) {
      throw new Error('Enter both the AWS access key ID and secret access key');
    }
  }

  if (!next.EC_API_KEY && !process.env.EC_API_KEY) {
    throw new Error('Enter an Elastic Cloud API key');
  }

  const temporaryPath = `${credentialsPath}.${process.pid}.tmp`;
  await fs.writeFile(temporaryPath, serialize(next), { mode: 0o600 });
  await fs.rename(temporaryPath, credentialsPath);
  await fs.chmod(credentialsPath, 0o600);

  for (const key of managedKeys) {
    const oldValue = previous[key];
    const newValue = next[key];
    if (newValue) {
      process.env[key] = newValue;
    } else if (oldValue && process.env[key] === oldValue) {
      delete process.env[key];
    }
  }

  return statusFrom(next);
}
