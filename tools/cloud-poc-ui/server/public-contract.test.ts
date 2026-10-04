import { promises as fs } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const publicDirectory = path.resolve(import.meta.dirname, '../public');

describe('credential form feedback', () => {
  it('provides an accessible inline status region', async () => {
    const html = await fs.readFile(
      path.join(publicDirectory, 'index.html'),
      'utf8',
    );
    expect(html).toContain('id="credentials-status"');
    expect(html).toContain('role="status"');
    expect(html).toContain('aria-live="polite"');
    expect(html).toContain('id="applicationCredentialsFile"');
    expect(html).toContain('accept="application/json,.json"');
  });

  it('shows saving, success, and failure feedback and restores the button', async () => {
    const script = await fs.readFile(
      path.join(publicDirectory, 'app.js'),
      'utf8',
    );
    expect(script).toContain("credentialsButton.textContent = 'Saving…'");
    expect(script).toContain('Credentials saved locally');
    expect(script).toContain('Credentials were not saved:');
    expect(script).toContain(
      "credentialsButton.textContent = 'Save local credentials'",
    );
    expect(script).toContain('credentialsForm.reset()');
    expect(script).not.toContain('event.currentTarget.reset()');
    expect(script).toContain(
      'values.applicationCredentialsJson = await uploadedCredential.text()',
    );
  });
});
