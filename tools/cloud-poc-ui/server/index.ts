import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createApp } from './app.js';
import { FixedCommandRunner } from './commands.js';
import { readCredentialStatus } from './credentials.js';
import { OperationStore } from './operation-store.js';
import { GcpProvider } from './providers/gcp.js';

const packageDirectory = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '..',
);
const repoRoot = path.resolve(packageDirectory, '../..');
const localDirectory = path.join(packageDirectory, '.cloud-poc');
const credentialsPath = path.join(localDirectory, 'credentials.env');
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
const port = Number(process.env.CLOUD_POC_UI_PORT ?? 5603);
if (!Number.isInteger(port) || port < 1024 || port > 65_535) {
  throw new Error('CLOUD_POC_UI_PORT must be an integer between 1024 and 65535');
}

const { app } = createApp({
  provider,
  operationStore,
  credentialsPath,
  staticDirectory: path.join(packageDirectory, 'public'),
});
app.listen(port, '127.0.0.1', () => {
  console.log(`Elastic Cloud PoC Builder: http://127.0.0.1:${port}`);
  console.log('Credential and operation files are local and owner-only.');
});
