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
    expect(html).toContain('id="guided-summary"');
    expect(html).toContain('id="configuration"');
    expect(html).toContain('id="elasticLabelsRequired"');
    expect(html).toContain('Elastic internal labels required');
    expect(html).toContain('id="configuration-status"');
    expect(html).toContain('Advanced: current raw output');
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
    expect(script).toContain('steps complete for');
    expect(script).toContain("'Needs attention'");
    expect(script).toContain("'Complete'");
    expect(script).toContain("'Locked'");
    expect(script).toContain("'Advanced: raw output'");
    expect(script).toContain("'Planned actions'");
    expect(script).toContain('appendFriendlyResult(card, step, record)');
    expect(script).toContain("'Approval required'");
    expect(script).toContain("'Apply reviewed plan'");
    expect(script).toContain("'Replan required'");
    expect(script).toContain("'Regenerate saved plan'");
    expect(script).toContain('The previous plan is stale after a failed apply');
    expect(script).toContain("api('/api/configuration'");
    expect(script).toContain('Save them before creating a Terraform plan');
    expect(script).toContain("'Account labels'");
    expect(script).toContain('Elastic internal labels enabled');
    expect(script).not.toContain(
      "window.prompt('Type APPLY to apply the reviewed saved plan.')",
    );
  });
});
