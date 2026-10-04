import path from 'node:path';
import { promises as fs } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { createApp } from './app.js';
import { FixedCommandRunner } from './commands.js';
import {
  loadCredentialEnvironment,
  readCredentialStatus,
} from './credentials.js';
import { OperationStore } from './operation-store.js';
import { GcpProvider } from './providers/gcp.js';
import { GcpVisibilityBackend } from './gcp-visibility-backend.js';
import { GcpVisibilityService } from './visibility.js';

const packageDirectory = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '..',
);
const repoRoot = path.resolve(packageDirectory, '../..');
const localDirectory = path.join(packageDirectory, '.cloud-poc');
const credentialsPath = path.join(localDirectory, 'credentials.env');
await loadCredentialEnvironment(credentialsPath);
const terraformDirectory = path.join(repoRoot, 'examples/gcp');
const operationStore = new OperationStore(
  path.join(localDirectory, 'operations.json'),
);
const provider = new GcpProvider(
  terraformDirectory,
  path.join(localDirectory, 'artifacts'),
  new FixedCommandRunner(),
  () => readCredentialStatus(credentialsPath),
);
const visibilityBackend = GcpVisibilityBackend.fromEnvironment(
  path.join(localDirectory, 'visibility-managed.json'),
);
const visibilityService = new GcpVisibilityService(
  path.join(localDirectory, 'visibility-state.json'),
  visibilityBackend,
);
const port = Number(process.env.CLOUD_POC_UI_PORT ?? 5603);
if (!Number.isInteger(port) || port < 1024 || port > 65_535) {
  throw new Error('CLOUD_POC_UI_PORT must be an integer between 1024 and 65535');
}

const { app } = createApp({
  provider,
  operationStore,
  credentialsPath,
  staticDirectory: path.join(packageDirectory, 'public'),
  visibility: {
    service: visibilityService,
    loadAnalysis: async () =>
      JSON.parse(
        await fs.readFile(
          path.join(localDirectory, 'artifacts/gcp-analysis.json'),
          'utf8',
        ),
      ) as unknown,
  },
});
app.listen(port, '127.0.0.1', () => {
  console.log(`Elastic Cloud PoC Builder: http://127.0.0.1:${port}`);
  console.log('Credential and operation files are local and owner-only.');
});
