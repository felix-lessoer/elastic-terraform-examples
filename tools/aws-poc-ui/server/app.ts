import crypto from 'node:crypto';
import path from 'node:path';
import type { NextFunction, Request, Response } from 'express';
import express from 'express';
import { ZodError } from 'zod';
import {
  readDeploymentConfig,
  repoRoot,
  terraformDirectory,
  writeDeploymentConfig,
} from './config.js';
import { runElasticWorkflow } from './elastic.js';
import { RunManager } from './run-manager.js';
import {
  deploymentStatus,
  runPreflight,
  terraformApply,
  terraformInit,
  terraformPlan,
} from './terraform.js';

const allowedOrigin = (origin: string | undefined): boolean => {
  if (!origin) return true;
  try {
    const url = new URL(origin);
    return (
      url.protocol === 'http:' &&
      (url.hostname === '127.0.0.1' || url.hostname === 'localhost')
    );
  } catch {
    return false;
  }
};

export function createApp(options?: {
  runManager?: RunManager;
  csrfToken?: string;
  serveStatic?: boolean;
}) {
  const app = express();
  const runs = options?.runManager ?? new RunManager();
  const csrfToken = options?.csrfToken ?? crypto.randomBytes(32).toString('hex');

  app.disable('x-powered-by');
  app.use(express.json({ limit: '100kb' }));

  app.get('/api/bootstrap', async (_request, response) => {
    response.json({
      csrfToken,
      repoRoot,
      terraformDirectory,
      status: await deploymentStatus(),
    });
  });

  app.get('/api/config', async (_request, response) => {
    response.json(await readDeploymentConfig());
  });

  app.get('/api/status', async (_request, response) => {
    response.json(await deploymentStatus());
  });

  app.get('/api/runs', (_request, response) => {
    response.json(runs.list());
  });

  app.get('/api/runs/:id/events', (request, response) => {
    const run = runs.get(request.params.id);
    if (!run) {
      response.status(404).json({ message: 'Run not found' });
      return;
    }

    response.setHeader('Content-Type', 'text/event-stream');
    response.setHeader('Cache-Control', 'no-cache, no-transform');
    response.setHeader('Connection', 'keep-alive');
    response.flushHeaders();

    const send = (record: unknown) => {
      response.write(`data: ${JSON.stringify(record)}\n\n`);
    };
    send(run);

    const listener = (record: unknown) => send(record);
    runs.events.on(run.id, listener);
    const heartbeat = setInterval(() => response.write(': heartbeat\n\n'), 15_000);
    request.on('close', () => {
      clearInterval(heartbeat);
      runs.events.off(run.id, listener);
    });
  });

  app.use('/api', (request, response, next) => {
    if (request.method === 'GET' || request.method === 'HEAD') {
      next();
      return;
    }
    if (!allowedOrigin(request.get('origin'))) {
      response.status(403).json({ message: 'Only localhost origins are allowed' });
      return;
    }
    if (request.get('x-aws-poc-csrf') !== csrfToken) {
      response.status(403).json({ message: 'Invalid CSRF token' });
      return;
    }
    next();
  });

  app.put('/api/config', async (request, response) => {
    const config = await writeDeploymentConfig(request.body);
    response.json({ config, saved: true });
  });

  app.post('/api/runs/:step', (request, response) => {
    const tasks = {
      preflight: {
        title: 'Check workstation and cloud prerequisites',
        task: runPreflight,
      },
      init: {
        title: 'Initialize Terraform',
        task: terraformInit,
      },
      plan: {
        title: 'Create Terraform deployment plan',
        task: terraformPlan,
      },
      apply: {
        title: 'Apply reviewed Terraform plan',
        task: terraformApply,
      },
    } as const;

    const step = request.params.step as keyof typeof tasks;
    const definition = tasks[step];
    if (!definition) {
      response.status(404).json({ message: 'Unknown operation' });
      return;
    }
    if (step === 'apply' && request.body?.confirmation !== 'APPLY') {
      response.status(400).json({
        message: 'Applying infrastructure requires confirmation value APPLY',
      });
      return;
    }

    try {
      const run = runs.start(step, definition.title, definition.task);
      response.status(202).json(run);
    } catch (error) {
      response.status(409).json({
        message: error instanceof Error ? error.message : String(error),
      });
    }
  });

  app.post('/api/workflows/:id/run', (request, response) => {
    const workflowId = request.params.id;
    if (!/^[a-z0-9][a-z0-9-]{1,127}$/.test(workflowId)) {
      response.status(400).json({ message: 'Invalid workflow ID' });
      return;
    }
    try {
      const run = runs.start(
        `workflow:${workflowId}`,
        `Run ${workflowId}`,
        (write) => runElasticWorkflow(workflowId, write),
      );
      response.status(202).json(run);
    } catch (error) {
      response.status(409).json({
        message: error instanceof Error ? error.message : String(error),
      });
    }
  });

  if (options?.serveStatic !== false) {
    const distribution = path.join(repoRoot, 'tools/aws-poc-ui/dist');
    app.use(express.static(distribution, { index: false }));
    app.use((request, response, next) => {
      if (
        request.method === 'GET' &&
        request.accepts('html') &&
        !request.path.startsWith('/api/')
      ) {
        response.sendFile(path.join(distribution, 'index.html'));
        return;
      }
      next();
    });
  }

  app.use(
    (
      error: unknown,
      _request: Request,
      response: Response,
      _next: NextFunction,
    ) => {
      if (error instanceof ZodError) {
        response.status(400).json({
          message: 'Invalid configuration',
          issues: error.issues,
        });
        return;
      }
      console.error(error);
      response.status(500).json({
        message: error instanceof Error ? error.message : 'Unexpected error',
      });
    },
  );

  return { app, runs, csrfToken };
}
