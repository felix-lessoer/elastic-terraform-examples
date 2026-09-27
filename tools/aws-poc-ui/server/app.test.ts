import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import request from 'supertest';
import { describe, expect, it } from 'vitest';
import { createApp } from './app.js';
import {
  defaultDeploymentConfig,
  deploymentConfigSchema,
} from './config.js';
import { saveCredentialsAt } from './credentials.js';
import { sanitizeTerraformOutputs } from './terraform.js';

describe('local API security', () => {
  it('does not expose a framework header and returns a CSRF token', async () => {
    const { app } = createApp({
      csrfToken: 'test-token',
      serveStatic: false,
    });
    const response = await request(app).get('/api/bootstrap').expect(200);
    expect(response.headers['x-powered-by']).toBeUndefined();
    expect(response.body.csrfToken).toBe('test-token');
  });

  it('rejects mutations without the local CSRF token', async () => {
    const { app } = createApp({
      csrfToken: 'test-token',
      serveStatic: false,
    });
    await request(app).post('/api/runs/plan').send({}).expect(403);
  });

  it('rejects non-local browser origins', async () => {
    const { app } = createApp({
      csrfToken: 'test-token',
      serveStatic: false,
    });
    await request(app)
      .post('/api/runs/plan')
      .set('Origin', 'https://attacker.example')
      .set('x-aws-poc-csrf', 'test-token')
      .send({})
      .expect(403);
  });

  it('requires explicit confirmation before apply', async () => {
    const { app } = createApp({
      csrfToken: 'test-token',
      serveStatic: false,
    });
    const response = await request(app)
      .post('/api/runs/apply')
      .set('Origin', 'http://127.0.0.1:5173')
      .set('x-aws-poc-csrf', 'test-token')
      .send({})
      .expect(400);
    expect(response.body.message).toContain('APPLY');
  });

  it('reports credential presence without returning credential values', async () => {
    const previous = process.env.EC_API_KEY;
    process.env.EC_API_KEY = 'elastic-secret-that-must-not-leak';
    try {
      const { app } = createApp({
        csrfToken: 'test-token',
        serveStatic: false,
      });
      const response = await request(app).get('/api/credentials').expect(200);
      expect(response.body.elasticCloudApiKey.configured).toBe(true);
      expect(response.text).not.toContain('elastic-secret-that-must-not-leak');
    } finally {
      if (previous === undefined) delete process.env.EC_API_KEY;
      else process.env.EC_API_KEY = previous;
    }
  });
});

describe('deployment configuration', () => {
  it('accepts the documented default configuration', () => {
    expect(deploymentConfigSchema.parse(defaultDeploymentConfig)).toEqual(
      defaultDeploymentConfig,
    );
  });

  it('allows tags to be omitted unless Elastic tags are required', () => {
    expect(
      deploymentConfigSchema.parse({
        ...defaultDeploymentConfig,
        elastic_tags_required: false,
        company_tags: {},
        required_tag_keys: [],
      }).company_tags,
    ).toEqual({});
    expect(() =>
      deploymentConfigSchema.parse({
        ...defaultDeploymentConfig,
        elastic_tags_required: true,
        company_tags: {},
      }),
    ).toThrow();
  });

  it('rejects invalid AWS regions and empty required tags', () => {
    expect(() =>
      deploymentConfigSchema.parse({
        ...defaultDeploymentConfig,
        aws_region: 'not a region',
      }),
    ).toThrow();
    expect(() =>
      deploymentConfigSchema.parse({
        ...defaultDeploymentConfig,
        company_tags: {
          ...defaultDeploymentConfig.company_tags,
          team: '',
        },
      }),
    ).toThrow();
  });
});

describe('credential persistence', () => {
  it('writes a reusable owner-only dotenv file and updates the process environment', async () => {
    const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'aws-poc-ui-'));
    const filePath = path.join(directory, '.env');
    const environment: NodeJS.ProcessEnv = {};
    try {
      const status = await saveCredentialsAt(
        filePath,
        {
          elasticCloudApiKey: 'elastic-test-key',
          awsMode: 'accessKeys',
          awsAccessKeyId: 'AKIATESTVALUE',
          awsSecretAccessKey: 'aws-test-secret',
          awsSessionToken: 'aws-test-session',
          awsProfile: '',
        },
        environment,
      );

      const file = await fs.readFile(filePath, 'utf8');
      const fileMode = (await fs.stat(filePath)).mode & 0o777;
      expect(fileMode).toBe(0o600);
      expect(file).toContain('EC_API_KEY="elastic-test-key"');
      expect(file).toContain('AWS_ACCESS_KEY_ID="AKIATESTVALUE"');
      expect(environment.AWS_SECRET_ACCESS_KEY).toBe('aws-test-secret');
      expect(status.elasticCloudApiKey.saved).toBe(true);
      expect(status.aws.saved).toBe(true);
      expect(JSON.stringify(status)).not.toContain('aws-test-secret');
    } finally {
      await fs.rm(directory, { recursive: true, force: true });
    }
  });
});

describe('Terraform output filtering', () => {
  it('allows only non-sensitive guided UI outputs', () => {
    expect(
      sanitizeTerraformOutputs({
        kibana_url: { sensitive: false, value: 'https://kibana.example' },
        workflow_ids: { sensitive: false, value: ['coverage'] },
        password: { sensitive: true, value: 'must-not-leak' },
        existing_log_sources: {
          sensitive: false,
          value: [{ secret: 'unbounded output' }],
        },
      }),
    ).toEqual({
      kibana_url: 'https://kibana.example',
      workflow_ids: ['coverage'],
    });
  });
});
