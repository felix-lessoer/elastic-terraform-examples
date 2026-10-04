import { describe, expect, it } from 'vitest';
import {
  commandArguments,
  FixedCommandRunner,
} from './commands.js';

describe('fixed command preflight failures', () => {
  it('plans the selected project with the required PoC labels', () => {
    const args = commandArguments('terraform.plan', {
      plan: '.cloud-poc-gcp.tfplan',
      projectId: 'valid-project1',
      companyLabels:
        '{"division":"field","org":"sa","environment":"poc"}',
      requiredLabelKeys: '["division","org","environment"]',
      elasticLabelsRequired: 'true',
    });
    expect(args).toContain('-var=google_cloud_project=valid-project1');
    expect(args).toContain(
      '-var=company_labels={"division":"field","org":"sa","environment":"poc"}',
    );
    expect(args).toContain(
      '-var=required_label_keys=["division","org","environment"]',
    );
    expect(args).toContain('-var=elastic_labels_required=true');
  });

  it('rejects arbitrary Terraform label arguments', () => {
    expect(() =>
      commandArguments('terraform.plan', {
        plan: '.cloud-poc-gcp.tfplan',
        projectId: 'valid-project1',
        companyLabels: '{"division":"field; touch /tmp/pwned"}',
        requiredLabelKeys: '["division"]',
        elasticLabelsRequired: 'true',
      }),
    ).toThrow('Invalid command value: companyLabels');
  });

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
