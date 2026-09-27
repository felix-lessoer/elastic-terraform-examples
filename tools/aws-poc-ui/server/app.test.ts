import request from 'supertest';
import { describe, expect, it } from 'vitest';
import { createApp } from './app.js';
import {
  defaultDeploymentConfig,
  deploymentConfigSchema,
} from './config.js';
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
});

describe('deployment configuration', () => {
  it('accepts the documented default configuration', () => {
    expect(deploymentConfigSchema.parse(defaultDeploymentConfig)).toEqual(
      defaultDeploymentConfig,
    );
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
