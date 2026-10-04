# Google Cloud Observe and Protect (modern PoC)

Creates:

1. **Elastic Security** serverless project (Complete) — Fleet agent for security data (audit/firewall), agentless CSPM, detection rules
2. **Elastic Observability** serverless project (Complete) — Fleet agent for observability data (metrics, vpcflow/dns/lb), linked to Security via **Cross-Project Search**
3. **Cockpit dashboard** on Observability — pinned Kibana NDJSON (`modules/cockpit-dashboard/cockpit.ndjson`, id `fcf1246c-…`) with aggregated alerts, data-flow, ML/AI inventory, GCP inventory via CPS, and `gcp-cockpit-recommendations`
4. **GCP Insight Engine** — resource-level coverage, deterministic
   recommendations, bounded read-only agent tools, ML keeper, and a final
   evidence-based summary
5. Bounded read-only Cloud Asset Inventory discovery with a local validated
   manifest and attach-to-existing Pub/Sub/Logging paths
6. GCP Pub/Sub topics + logging sinks, collector SA, company-policy labels
7. Two GCE Elastic Agents — one enrolled to Security Fleet, one to
   Observability Fleet, with stale-enrollment reconciliation

## Data split

| Project | Collects |
| --- | --- |
| Security | CSPM findings, GCP audit logs, GCP firewall logs, detection rules |
| Observability | Compute/storage/LB metrics, vpcflow, DNS, load-balancing logs |
| Cockpit (Obs + CPS) | Unified aggregated view of both |

## Company labels

Every labelable GCP resource gets your policy labels via `company_labels`. Values are normalized to GCP rules (lowercase, `[a-z0-9_-]`). Compute instances require a valid `division` label for org-policy constrained projects.

For internal Elastic accounts, keep `elastic_labels_required = true` and set
all keys in `required_label_keys`. Customer accounts can set it to `false`;
their `company_labels` map must still be non-empty, but Elastic-specific keys
are not enforced. The guided UI exposes this as an opt-in checklist and keeps
it off by default.

```hcl
company_labels = {
  division    = "field"
  cost-center = "platform"
  owner       = "sre-team"
  environment = "poc"
}
```

## Prerequisites

Terraform credentials need permission to create Compute Engine instances (Elastic Agent VMs), Pub/Sub, Logging sinks, and IAM bindings.

```bash
export EC_API_KEY="..."
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa.json
```

## Guided quick start

The local PoC Builder keeps credentials and manifests on the operator machine,
shows a readable saved Terraform plan, and separates read-only discovery from
paid telemetry enablement and workload mutation.

```bash
cd tools/cloud-poc-ui
npm install
npm start
```

Open `http://127.0.0.1:5603`. Direct Terraform remains available for advanced
automation:

```bash
cd examples/gcp
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform plan -out=gcp.tfplan
terraform show gcp.tfplan
terraform apply gcp.tfplan
rm -f gcp.tfplan
```

## Discovery and collection safety

Discovery is allow-listed, budgeted, and read-only. The complete manifest stays
local; Terraform receives only its path and persists its hash and non-sensitive
summary. Existing sinks, topics, and subscriptions can be attached by stream
key so customer-owned collection is not duplicated or destroyed.

The GCP Fleet package currently requires service-account JSON for these inputs.
That private key is therefore present in Terraform state even though it is
sensitive and never exposed as a root output. Use an encrypted remote backend,
restrict state access, rotate after the PoC, and destroy the collector identity
during cleanup. Prefer federation/impersonation as soon as the package supports
it.

GKE, Cloud Run, Cloud SQL, and Pub/Sub metrics are opt-in because they can
increase GCP Monitoring and Elastic ingest cost. Their workflows are not
deployed or executed until the corresponding metric flag is enabled. Check
`workflow_telemetry_status` for explicit `enabled` or
`skipped_missing_telemetry` status.

## What to open after apply

| Surface | Where |
| --- | --- |
| Cockpit dashboard | `observability_kibana_url` → Dashboards → **GCP Observe & Protect Cockpit - updated** (or `cockpit_dashboard_url`) |
| Kibana Workflows | `examples/gcp/workflows/*.yaml` → deterministic service findings and `gcp-cockpit-insight-summary` |
| Security Fleet / CSPM | `kibana_url` — agent `elastic-poc-agent` |
| Observability Fleet | `observability_kibana_url` — agent `elastic-poc-obs-agent` |
| AI agents | Observability → Agent Builder (`gcp-security-analyst`, `gcp-obs-triage`) |

Toggle Observability hub with `enable_observability_project = false` if you only want Security.

## Cleanup

Rollback optional visibility adapters from the PoC Builder before destroying
Terraform resources. Then review `terraform plan -destroy`, apply that exact
plan, and confirm customer-owned collection resources in
`collection_ownership` remain intact.
