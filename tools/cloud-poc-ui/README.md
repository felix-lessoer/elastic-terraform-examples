# Shared Cloud PoC Builder (GCP path)

This package is an incremental shared provider/server contract. It does not
move or change `tools/aws-poc-ui`; the proven AWS guided path remains usable
while GCP integration is developed behind a typed provider.

## Run locally

```bash
cd tools/cloud-poc-ui
npm install
npm test
npm run typecheck
npm start
```

The server always listens on `127.0.0.1` (port `5603` by default). Mutating API
requests require both a localhost `Origin` and the CSRF token returned by
`GET /api/bootstrap`.

The guided GCP operations are:

1. `preflight`
2. `terraform-init`
3. `terraform-plan` (returns a readable, value-free action table)
4. `terraform-apply` (requires `confirmation: "APPLY"`)
5. `discovery`
6. `analysis`
7. `workflows`
8. `final-links`

Only fixed server-side command IDs can execute. Project IDs and saved-plan
names are validated before command construction. Local credentials, discovery
artifacts, operation history, snapshots, and rollback state are written under
`.cloud-poc/` with owner-only directory/file modes and are gitignored.

## Provider and adapter integration

`CloudProvider` is the shared UI/server boundary. `GcpProvider` currently uses
Cloud Asset Inventory for a bounded local manifest and generates deterministic,
named Cloud Run, GKE, and Cloud SQL visibility candidates. The manifest stays
local; operation results contain only its hash and summary.

`VisibilityBackend` is intentionally narrow. A production implementation must
use resource-specific credentials and implement snapshot, deploy, signal
validation, rollback, managed-deployment listing, and orphan cleanup. The
shared orchestrator enforces explicit GCP/Elastic cost and workload-impact
acknowledgement, persists rollback state, auto-rolls back failed validation,
and skips inactive/unsupported candidates without mutation.

The workflow operation currently validates the fixed GCP workflow allow-list
and exposes the executor seam. Wiring an authenticated Elastic workflow
executor and a concrete GCP visibility backend are deployment integration
steps; neither is faked by this local contract.
