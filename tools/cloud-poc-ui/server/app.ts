import crypto from 'node:crypto';
import type { NextFunction, Request, Response } from 'express';
import express from 'express';
import { z, ZodError } from 'zod';
import type {
  CloudProvider,
  GuidedOperation,
  OperationRequest,
} from './cloud-provider.js';
import { readCredentialStatus, saveCredentials } from './credentials.js';
import { OperationStore } from './operation-store.js';
import {
  type GcpVisibilityService,
  type VisibilityCandidate,
  visibilityCandidateId,
} from './visibility.js';

const operations = new Set<GuidedOperation>([
  'preflight',
  'terraform-init',
  'terraform-plan',
  'terraform-apply',
  'discovery',
  'analysis',
  'workflows',
  'final-links',
]);
const operationSchema = z
  .object({
    projectId: z.string().regex(/^[a-z][a-z0-9-]{4,61}[a-z0-9]$/),
    confirmation: z.string().max(32).optional(),
    workflowIds: z
      .array(z.string().regex(/^[a-z0-9][a-z0-9-]{1,127}$/))
      .max(20)
      .optional(),
  })
  .strict();
const visibilityCandidateSchema = z
  .object({
    id: z.string().min(1).max(128),
    name: z.string().min(1).max(1024),
    resourceId: z.string().min(1).max(4096),
    resourceType: z.string().min(1).max(256),
    kind: z.enum(['cloud-run-traces', 'gke-metrics', 'cloud-sql-insights']),
    eligibility: z.enum(['eligible', 'inactive', 'unsupported']),
    reason: z.string().max(4096).optional(),
    cost: z.object({
      gcp: z.string().min(1).max(4096),
      elastic: z.string().min(1).max(4096),
    }),
    workloadImpact: z.string().min(1).max(4096),
    validation: z.string().min(1).max(4096),
    rollback: z.string().min(1).max(4096),
  })
  .strict();
const deploySchema = z
  .object({
    costAccepted: z.literal(true),
    impactAccepted: z.literal(true),
  })
  .strict();
const skipSchema = z
  .object({ reason: z.string().trim().min(1).max(1000) })
  .strict();
const cleanupSchema = z
  .object({ confirmation: z.literal('CLEANUP ORPHANS') })
  .strict();

export function isLocalOrigin(origin: string | undefined): boolean {
  if (!origin) return false;
  try {
    const url = new URL(origin);
    return (
      url.protocol === 'http:' &&
      (url.hostname === '127.0.0.1' ||
        url.hostname === 'localhost' ||
        url.hostname === '[::1]')
    );
  } catch {
    return false;
  }
}

export function createApp(options: {
  provider: CloudProvider;
  operationStore: OperationStore;
  credentialsPath: string;
  csrfToken?: string;
  environment?: NodeJS.ProcessEnv;
  staticDirectory?: string;
  visibility?: {
    service: GcpVisibilityService;
    loadAnalysis: () => Promise<unknown>;
  };
}) {
  const app = express();
  const csrfToken = options.csrfToken ?? crypto.randomBytes(32).toString('hex');
  const environment = options.environment ?? process.env;

  app.disable('x-powered-by');
  app.use(express.json({ limit: '100kb' }));
  app.use('/api', (_request, response, next) => {
    response.setHeader('Cache-Control', 'no-store');
    response.setHeader('X-Content-Type-Options', 'nosniff');
    next();
  });

  app.get('/api/bootstrap', async (_request, response) => {
    await options.operationStore.load();
    response.json({
      csrfToken,
      provider: {
        slug: options.provider.slug,
        displayName: options.provider.displayName,
      },
      credentials: await options.provider.credentialStatus(),
      operations: options.operationStore.list(),
    });
  });

  app.get('/api/credentials', async (_request, response) => {
    response.json(
      await readCredentialStatus(options.credentialsPath, environment),
    );
  });

  app.get('/api/operations', async (_request, response) => {
    await options.operationStore.load();
    response.json(options.operationStore.list());
  });

  app.get('/api/operations/:id/events', async (request, response) => {
    await options.operationStore.load();
    const record = options.operationStore.get(request.params.id);
    if (!record) {
      response.status(404).json({ message: 'Operation not found' });
      return;
    }
    response.setHeader('Content-Type', 'text/event-stream');
    response.setHeader('Cache-Control', 'no-cache, no-transform');
    response.flushHeaders();
    const send = (value: unknown) =>
      response.write(`data: ${JSON.stringify(value)}\n\n`);
    send(record);
    options.operationStore.events.on(record.id, send);
    const heartbeat = setInterval(() => response.write(': heartbeat\n\n'), 15_000);
    request.on('close', () => {
      clearInterval(heartbeat);
      options.operationStore.events.off(record.id, send);
    });
  });

  app.use('/api', (request, response, next) => {
    if (request.method === 'GET' || request.method === 'HEAD') return next();
    if (!isLocalOrigin(request.get('origin'))) {
      response.status(403).json({ message: 'A localhost browser origin is required' });
      return;
    }
    if (request.get('x-cloud-poc-csrf') !== csrfToken) {
      response.status(403).json({ message: 'Invalid CSRF token' });
      return;
    }
    next();
  });

  app.put('/api/credentials', async (request, response) => {
    response.json(
      await saveCredentials(options.credentialsPath, request.body, environment),
    );
  });

  app.post('/api/providers/gcp/operations/:operation', async (request, response) => {
    const operation = request.params.operation as GuidedOperation;
    if (!operations.has(operation)) {
      response.status(404).json({ message: 'Unknown guided operation' });
      return;
    }
    const input: OperationRequest = operationSchema.parse(request.body);
    if (operation === 'terraform-apply' && input.confirmation !== 'APPLY') {
      response.status(400).json({ message: 'Confirmation APPLY is required' });
      return;
    }
    try {
      const record = await options.operationStore.start(
        operation,
        (context) => options.provider.execute(operation, input, context),
        input.projectId,
      );
      response.status(202).json(record);
    } catch (error) {
      response.status(409).json({
        message: error instanceof Error ? error.message : String(error),
      });
    }
  });

  const loadCandidates = async (): Promise<VisibilityCandidate[]> => {
    if (!options.visibility) throw new Error('Visibility lifecycle is not configured');
    const analysis = z
      .object({ candidates: z.array(visibilityCandidateSchema).max(5000) })
      .parse(await options.visibility.loadAnalysis());
    return analysis.candidates.map((candidate) => {
      if (candidate.id !== visibilityCandidateId(candidate.resourceId, candidate.kind)) {
        throw new Error('Persisted analysis contains an invalid candidate binding');
      }
      return options.visibility!.service.prepare(candidate);
    });
  };
  const requireCandidate = async (candidateId: string) => {
    const candidate = (await loadCandidates()).find(
      (item) => item.id === candidateId,
    );
    if (!candidate) throw new Error('Candidate is not present in the local analysis');
    return candidate;
  };
  const visibilityMutation = (
    handler: (request: Request, response: Response) => Promise<void>,
  ) => async (request: Request, response: Response, next: NextFunction) => {
    try {
      await handler(request, response);
    } catch (error) {
      if (error instanceof ZodError) return next(error);
      response.status(409).json({
        message: error instanceof Error ? error.message : String(error),
      });
    }
  };

  app.get('/api/providers/gcp/visibility', async (_request, response, next) => {
    try {
      if (!options.visibility) {
        response.status(404).json({ message: 'Visibility lifecycle is not configured' });
        return;
      }
      const candidates = await loadCandidates();
      const records = (await options.visibility.service.records()).map(
        ({ candidate, snapshot: _snapshot, ...record }) => ({
          ...record,
          candidateId: candidate.id,
        }),
      );
      response.json({ candidates, records });
    } catch (error) {
      if (error instanceof ZodError) return next(error);
      response.status(409).json({
        message:
          error instanceof Error && 'code' in error && error.code === 'ENOENT'
            ? 'Run GCP analysis before loading visibility candidates'
            : error instanceof Error
              ? error.message
              : String(error),
      });
    }
  });

  app.post(
    '/api/providers/gcp/visibility/candidates/:candidateId/deploy',
    visibilityMutation(async (request, response) => {
      const candidate = await requireCandidate(
        z.string().parse(request.params.candidateId),
      );
      if (candidate.eligibility !== 'eligible') {
        throw new Error(candidate.reason ?? `Candidate is ${candidate.eligibility}`);
      }
      const approval = deploySchema.parse(request.body);
      const record = await options.visibility!.service.deploy(candidate, approval);
      response.json({ ...record, snapshot: undefined });
    }),
  );

  app.post(
    '/api/providers/gcp/visibility/candidates/:candidateId/rollback',
    visibilityMutation(async (request, response) => {
      z.object({}).strict().parse(request.body);
      const candidate = await requireCandidate(
        z.string().parse(request.params.candidateId),
      );
      const existing = (await options.visibility!.service.records()).find(
        (record) => record.candidate.id === candidate.id,
      );
      if (
        existing &&
        (existing.candidate.resourceId !== candidate.resourceId ||
          existing.candidate.kind !== candidate.kind)
      ) {
        throw new Error('Persisted rollback target no longer matches the analysis');
      }
      const record = await options.visibility!.service.rollback(candidate.id);
      response.json({ ...record, snapshot: undefined });
    }),
  );

  app.post(
    '/api/providers/gcp/visibility/candidates/:candidateId/skip',
    visibilityMutation(async (request, response) => {
      const candidate = await requireCandidate(
        z.string().parse(request.params.candidateId),
      );
      const { reason } = skipSchema.parse(request.body);
      const record = await options.visibility!.service.skip(candidate, reason);
      response.json(record);
    }),
  );

  app.post(
    '/api/providers/gcp/visibility/orphans/cleanup',
    visibilityMutation(async (request, response) => {
      cleanupSchema.parse(request.body);
      response.json({
        cleanedDeploymentIds:
          await options.visibility!.service.cleanupOrphans(),
      });
    }),
  );

  if (options.staticDirectory) {
    app.use(express.static(options.staticDirectory, { index: 'index.html' }));
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
          message: 'Invalid request',
          issues: error.issues,
        });
        return;
      }
      console.error(error);
      response.status(500).json({ message: 'Unexpected local server error' });
    },
  );
  return { app, csrfToken };
}
