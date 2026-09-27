import { createApp } from './app.js';

const port = Number(process.env.AWS_POC_UI_PORT ?? 5602);
if (!Number.isInteger(port) || port < 1024 || port > 65_535) {
  throw new Error('AWS_POC_UI_PORT must be an integer between 1024 and 65535');
}

const { app } = createApp();
app.listen(port, '127.0.0.1', () => {
  console.log(`Elastic AWS PoC Guide: http://127.0.0.1:${port}`);
  console.log('Credentials remain in this local process and are not sent to the browser.');
});
