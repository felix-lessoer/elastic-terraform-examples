import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  findUnmappedGcpServices,
  readGcpManifestWithHash,
  recommendGcpIntegrations,
} from './gcp-integrations.js';

describe('GCP customer integration catalog', () => {
  it('recommends discovered optional services and preserves core value', () => {
    const recommendations = recommendGcpIntegrations({
      approved_projects: ['customer-project1'],
      resources: [
        {
          kind: 'asset',
          asset_type: 'container.googleapis.com/Cluster',
        },
        {
          kind: 'enabled_service',
          name: 'projects/123/services/redis.googleapis.com',
        },
      ],
    });
    expect(recommendations).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: 'audit',
          mode: 'core',
          recommended: true,
        }),
        expect.objectContaining({
          id: 'gke',
          discovered: true,
          recommended: true,
        }),
        expect.objectContaining({
          id: 'redis',
          discovered: true,
          recommended: true,
        }),
        expect.objectContaining({
          id: 'cloudsql',
          discovered: false,
          recommended: false,
        }),
        expect.objectContaining({
          id: 'billing',
          requiresConfiguration: true,
          selectedByDefault: false,
        }),
      ]),
    );
  });

  it('binds selections to the exact owner-only manifest bytes', async () => {
    const directory = await fs.mkdtemp(
      path.join(os.tmpdir(), 'gcp-integrations-'),
    );
    try {
      const filePath = path.join(directory, 'gcp-manifest.json');
      await fs.writeFile(
        filePath,
        '{"approved_projects":["customer-project1"],"resources":[]}\n',
        { mode: 0o600 },
      );
      const first = await readGcpManifestWithHash(filePath);
      await fs.appendFile(filePath, ' ');
      const second = await readGcpManifestWithHash(filePath);
      expect(first.manifestHash).toMatch(/^[a-f0-9]{64}$/);
      expect(second.manifestHash).not.toBe(first.manifestHash);
    } finally {
      await fs.rm(directory, { recursive: true, force: true });
    }
  });

  it('surfaces enabled APIs that are not silently supported', () => {
    expect(
      findUnmappedGcpServices({
        approved_projects: ['customer-project1'],
        resources: [
          {
            kind: 'enabled_service',
            name: 'projects/123/services/spanner.googleapis.com',
          },
          {
            kind: 'enabled_service',
            name: 'projects/123/services/monitoring.googleapis.com',
          },
        ],
      }),
    ).toEqual(['spanner.googleapis.com']);
  });
});
