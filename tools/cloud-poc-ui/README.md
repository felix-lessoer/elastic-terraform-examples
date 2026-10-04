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

`terraform`, `gcloud`, and Python 3 must be available on the `PATH` of the
process that starts the UI. Live discovery also requires the `google-auth`
Python package. Preflight checks Terraform and Google Cloud CLI before querying
the selected project and reports an actionable missing-command error.

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

The optional adapter lifecycle is available after `analysis`. Its API and UI
only accept deterministic candidate IDs from the owner-only local
`gcp-analysis.json`; callers cannot supply resource IDs. Every mutation has the
same localhost-origin and CSRF controls as the guided operations. Snapshots,
managed-adapter ownership, and rollback state stay under `.cloud-poc/` in
owner-only files. Deployment requires explicit GCP/Elastic cost and workload
impact acknowledgement. Failed named-resource signal validation automatically
restores the snapshot. Explicit rollback, skip, and confirmed orphan cleanup
are exposed in the UI.

The only concrete mutation currently supported is Cloud SQL Query Insights. It
uses fixed `gcloud sql instances describe/patch` operations against the exact
project and instance parsed from the analyzed canonical resource name. Before
it is eligible, configure all three environment variables:

```bash
export CLOUD_POC_VISIBILITY_ELASTICSEARCH_URL=https://example.es.region.gcp.elastic-cloud.com
export CLOUD_POC_VISIBILITY_ELASTICSEARCH_API_KEY=... # Elasticsearch API key, not an Elastic Cloud API key
export CLOUD_POC_VISIBILITY_ELASTICSEARCH_INDEX='metrics-*'
```

The API key needs read access to the existing Google Cloud integration data.
Validation queries the configured index for a recent signal naming the exact
Cloud SQL resource or instance. It does not infer success from the patch.
Cloud Run remains unsupported because this repository has no safe application
instrumentation and revision-traffic restoration contract. GKE remains
unsupported because there is no reviewed collector manifest, narrow RBAC
contract, and rollback implementation. Both still appear in the candidate UI
with those reasons and cannot be deployed.

The workflow operation currently validates the fixed GCP workflow allow-list
and exposes the executor seam. Wiring an authenticated Elastic workflow
executor remains a deployment integration step and is not faked by this local
contract.
