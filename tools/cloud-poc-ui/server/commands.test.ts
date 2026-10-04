import { describe, expect, it } from 'vitest';
import { FixedCommandRunner } from './commands.js';

describe('fixed command preflight failures', () => {
  it('turns a missing executable into actionable feedback', async () => {
    const previousPath = process.env.PATH;
    process.env.PATH = '/definitely-missing';
    try {
      const result = await new FixedCommandRunner().run(
        'gcloud.version',
        {},
        { cwd: process.cwd(), write: () => undefined },
      );
      expect(result.exitCode).toBe(127);
      expect(result.stderr).toContain(
        'Required command "gcloud" is not installed or is not on PATH',
      );
      expect(result.stderr).toContain('restart the PoC Builder');
    } finally {
      process.env.PATH = previousPath;
    }
  });
});
