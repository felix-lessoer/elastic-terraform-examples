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
import { executeCommand } from './run-manager.js';
import {
  explainPreflightFailure,
  sanitizeTerraformOutputs,
  summarizeTerraformPlan,
} from './terraform.js';

describe('local API security', () => {
  it('does not expose a framework header and returns a CSRF token', async () => {
    const { app } = createApp({
      csrfToken: 'test-token',
      serveStatic: false,
    });
    const response = await request(app).get('/api/bootstrap').expect(200);
    expect(response.headers['x-powered-by']).toBeUndefined();
    expect(response.headers['cache-control']).toBe('no-store');
    expect(response.body.csrfToken).toBe('test-token');
  });

  it('rejects mutations without the local CSRF token', async () => {
    const { app } = createApp({
      csrfToken: 'test-token',
      serveStatic: false,
    });
    await request(app).post('/api/runs/plan').send({}).expect(403);
  });

  it('rejects Terraform initialization before preflight passes', async () => {
    const { app } = createApp({
      csrfToken: 'test-token',
      serveStatic: false,
    });
    const response = await request(app)
      .post('/api/runs/init')
      .set('Origin', 'http://127.0.0.1:5602')
      .set('x-aws-poc-csrf', 'test-token')
      .send({})
      .expect(409);
    expect(response.body.message).toContain('prerequisite');
  });

  it('rejects Terraform planning before cloud preflight passes', async () => {
    const { app } = createApp({
      csrfToken: 'test-token',
      serveStatic: false,
    });
    const response = await request(app)
      .post('/api/runs/plan')
      .set('Origin', 'http://127.0.0.1:5602')
      .set('x-aws-poc-csrf', 'test-token')
      .send({})
      .expect(409);
    expect(response.body.message).toContain('cloud prerequisite');
  });

  it('rejects malformed visibility expansion selections', async () => {
    const { app } = createApp({
      csrfToken: 'test-token',
      serveStatic: false,
    });
    const response = await request(app)
      .put('/api/visibility-expansions')
      .set('Origin', 'http://127.0.0.1:5602')
      .set('x-aws-poc-csrf', 'test-token')
      .send({ selectedProposalIds: ['not-a-proposal-id'] })
      .expect(400);
    expect(response.body.message).toContain('Invalid visibility');
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

  it('always marks generated configuration as Deployment Creator mode', () => {
    expect(defaultDeploymentConfig.deployment_creator_mode).toBe(true);
    expect(() =>
      deploymentConfigSchema.parse({
        ...defaultDeploymentConfig,
        deployment_creator_mode: false,
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

describe('command progress output', () => {
  it('redacts secrets supplied only to a child command', async () => {
    const logs: string[] = [];
    const secret = 'adapter-password-that-must-not-leak';
    await executeCommand(
      process.execPath,
      ['-e', 'process.stdout.write(process.env.KIBANA_PASSWORD)'],
      {
        cwd: os.tmpdir(),
        write: (line) => logs.push(line),
        env: { ...process.env, KIBANA_PASSWORD: secret },
      },
    );
    expect(logs.join('\n')).toContain('[REDACTED]');
    expect(logs.join('\n')).not.toContain(secret);
  });

  it('reports an actionable error when a required command is unavailable', async () => {
    const logs: string[] = [];
    const result = await executeCommand(
      'elastic-poc-command-that-does-not-exist',
      [],
      { cwd: os.tmpdir(), write: (line) => logs.push(line) },
    );
    expect(result.exitCode).not.toBe(0);
    expect(logs.join('\n')).toContain('ENOENT');
  });

  it('turns missing AWS CLI output into actionable guidance', () => {
    expect(
      explainPreflightFailure(
        'aws',
        'AWS identity',
        'spawn aws ENOENT',
        1,
      ),
    ).toContain('not installed');
  });

  it('turns expired AWS credentials into actionable guidance', () => {
    expect(
      explainPreflightFailure(
        'aws',
        'AWS identity',
        'ExpiredToken: The security token included in the request is expired',
        255,
      ),
    ).toContain('fresh temporary credentials');
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

describe('Terraform plan summary', () => {
  it('returns only reviewable managed resource metadata', () => {
    const summary = summarizeTerraformPlan({
      timestamp: '2026-09-27T18:00:00Z',
      resource_changes: [
        {
          address: 'aws_iam_role.collector',
          mode: 'managed',
          type: 'aws_iam_role',
          name: 'collector',
          change: {
            actions: ['create'],
            after: { secret_value: 'must-not-be-returned' },
          },
        },
        {
          address: 'module.stack.ec_deployment.project',
          module_address: 'module.stack',
          mode: 'managed',
          type: 'ec_deployment',
          name: 'project',
          change: { actions: ['delete', 'create'] },
        },
        {
          address: 'data.aws_caller_identity.current',
          mode: 'data',
          type: 'aws_caller_identity',
          name: 'current',
          change: { actions: ['read'] },
        },
      ],
    });
    expect(summary.counts.create).toBe(1);
    expect(summary.counts.replace).toBe(1);
    expect(summary.resources).toHaveLength(2);
    expect(JSON.stringify(summary)).not.toContain('must-not-be-returned');
  });
});
