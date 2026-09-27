import crypto from 'node:crypto';
import path from 'node:path';
import type { NextFunction, Request, Response } from 'express';
import express from 'express';
import { ZodError } from 'zod';
import {
  brownfieldStatus,
  deployVisibilityExpansions,
  readBrownfieldArtifact,
  reconcileDeployedVisibilityExpansions,
  rollbackVisibilityExpansions,
  runBrownfieldAnalysis,
  runBrownfieldDiscovery,
  saveVisibilitySelection,
  visibilityExpansionStatus,
} from './brownfield.js';
import {
  readDeploymentConfig,
  repoRoot,
  terraformDirectory,
  writeDeploymentConfig,
} from './config.js';
import {
  credentialsStatus,
  saveCredentials,
} from './credentials.js';
import {
  refreshElasticInsights,
  runElasticWorkflow,
} from './elastic.js';
import { RunManager } from './run-manager.js';
import {
  deploymentStatus,
  readPlanSummary,
  readSafeTerraformOutputs,
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
  app.use('/api', (_request, response, next) => {
    response.setHeader('Cache-Control', 'no-store');
    next();
  });

  app.get('/api/bootstrap', async (_request, response) => {
    response.json({
      csrfToken,
      repoRoot,
      terraformDirectory,
      status: await deploymentStatus(),
      credentials: await credentialsStatus(),
    });
  });

  app.get('/api/credentials', async (_request, response) => {
    response.json(await credentialsStatus());
  });

  app.get('/api/config', async (_request, response) => {
    response.json(await readDeploymentConfig());
  });

  app.get('/api/status', async (_request, response) => {
    response.json(await deploymentStatus());
  });

  app.get('/api/plan', async (_request, response) => {
    response.json(await readPlanSummary());
  });

  app.get('/api/brownfield', async (_request, response) => {
    response.json(await brownfieldStatus());
  });

  app.get('/api/visibility-expansions', async (_request, response) => {
    response.json(await visibilityExpansionStatus());
  });

  app.get('/api/brownfield/:artifact', async (request, response) => {
    if (request.params.artifact !== 'manifest' && request.params.artifact !== 'analysis') {
      response.status(404).json({ message: 'Unknown brownfield artifact' });
      return;
    }
    try {
      const contents = await readBrownfieldArtifact(request.params.artifact);
      response.type('application/json').send(contents);
    } catch (error) {
      response.status(404).json({
        message: error instanceof Error ? error.message : String(error),
      });
    }
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

  app.put('/api/credentials', async (request, response) => {
    response.json(await saveCredentials(request.body));
  });

  app.put('/api/visibility-expansions', async (request, response) => {
    try {
      response.json(await saveVisibilitySelection(request.body));
    } catch (error) {
      response.status(400).json({
        message: error instanceof Error ? error.message : String(error),
      });
    }
  });

  app.post('/api/visibility-expansions/deploy', (_request, response) => {
    try {
      response.status(202).json(
        runs.start(
          'visibility:deploy',
          'Deploy selected visibility canaries',
          deployVisibilityExpansions,
        ),
      );
    } catch (error) {
      response.status(409).json({
        message: error instanceof Error ? error.message : String(error),
      });
    }
  });

  app.post('/api/visibility-expansions/rollback', (_request, response) => {
    try {
      response.status(202).json(
        runs.start(
          'visibility:rollback',
          'Roll back visibility canaries',
          rollbackVisibilityExpansions,
        ),
      );
    } catch (error) {
      response.status(409).json({
        message: error instanceof Error ? error.message : String(error),
      });
    }
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
      discovery: {
        title: 'Discover existing AWS environment',
        task: runBrownfieldDiscovery,
      },
      analysis: {
        title: 'Analyze brownfield services and gaps',
        task: runBrownfieldAnalysis,
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
    if (step === 'init') {
      const preflight = runs.list().find((run) => run.step === 'preflight');
      const result = preflight?.result as
        | {
            checks?: Array<{ id: string; status: string }>;
          }
        | undefined;
      const initializationReady =
        preflight?.status === 'succeeded' &&
        ['configuration', 'terraform'].every((id) =>
          result?.checks?.some(
            (check) => check.id === id && check.status === 'passed',
          ),
        );
      if (!initializationReady) {
        response.status(409).json({
          message: 'Pass the Terraform and configuration prerequisite checks before initializing',
        });
        return;
      }
    }
    if (step === 'plan') {
      const preflight = runs.list().find((run) => run.step === 'preflight');
      const result = preflight?.result as { passed?: boolean } | undefined;
      if (preflight?.status !== 'succeeded' || result?.passed !== true) {
        response.status(409).json({
          message: 'Pass all cloud prerequisite checks before creating a plan',
        });
        return;
      }
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

  app.post('/api/workflows/run-all', (_request, response) => {
    try {
      const run = runs.start(
        'workflows:all',
        'Refresh Elastic insights',
        async (write) => {
          await reconcileDeployedVisibilityExpansions(write);
          return refreshElasticInsights(write);
        },
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
