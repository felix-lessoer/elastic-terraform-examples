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
      manifestPath: '/tmp/gcp-manifest.json',
      companyLabels:
        '{"division":"field","org":"sa","environment":"poc"}',
      requiredLabelKeys: '["division","org","environment"]',
      elasticLabelsRequired: 'true',
      selectedServiceIds:
        '["cspm","audit","compute","gke","firestore"]',
      billingDatasetId: '',
    });
    expect(args).toContain('-var=google_cloud_project=valid-project1');
    expect(args).toContain(
      '-var=company_labels={"division":"field","org":"sa","environment":"poc"}',
    );
    expect(args).toContain(
      '-var=required_label_keys=["division","org","environment"]',
    );
    expect(args).toContain('-var=elastic_labels_required=true');
    expect(args).toContain(
      '-var=gcp_discovery_manifest_path=/tmp/gcp-manifest.json',
    );
    expect(args).toContain('-var=enable_gke_metrics=true');
    expect(args).toContain('-var=enable_firestore_metrics=true');
    expect(args).toContain('-var=enable_cloudsql_metrics=false');
    expect(args).toContain('-var=enable_billing_metrics=false');
  });

  it('rejects arbitrary Terraform label arguments', () => {
    expect(() =>
      commandArguments('terraform.plan', {
        plan: '.cloud-poc-gcp.tfplan',
        projectId: 'valid-project1',
        manifestPath: '/tmp/gcp-manifest.json',
        companyLabels: '{"division":"field; touch /tmp/pwned"}',
        requiredLabelKeys: '["division"]',
        elasticLabelsRequired: 'true',
        selectedServiceIds: '[]',
        billingDatasetId: '',
      }),
    ).toThrow('Invalid command value: companyLabels');
  });

  it('rejects integration IDs outside the server allow-list', () => {
    expect(() =>
      commandArguments('terraform.plan', {
        plan: '.cloud-poc-gcp.tfplan',
        projectId: 'valid-project1',
        manifestPath: '/tmp/gcp-manifest.json',
        companyLabels: '{"owner":"poc"}',
        requiredLabelKeys: '[]',
        elasticLabelsRequired: 'false',
        selectedServiceIds: '["arbitrary-shell-hook"]',
        billingDatasetId: '',
      }),
    ).toThrow('Invalid command value: selectedServiceIds');
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
