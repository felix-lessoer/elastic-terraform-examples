# Pinned Kibana Workflow YAML — GCP cockpit insight fabric

These workflows (plus the cross-project seeder) power Datadog-comparable
insights on the Observability cockpit. Filenames are stable `workflow_id`s
deployed by `module.workflows_obs`.

| File | Writes to | Purpose |
| --- | --- | --- |
| `gcp-cockpit-cloudrun-recommendations.yaml` | `gcp-cockpit-recommendations` | Cloud Run 5xx rate + idle instances |
| `gcp-cockpit-cloudsql-recommendations.yaml` | `gcp-cockpit-recommendations` | Cloud SQL high memory utilization |
| `gcp-cockpit-gke-recommendations.yaml` | `gcp-cockpit-recommendations` | Underutilized GKE nodes |
| `gcp-cockpit-host-recommendations.yaml` | `gcp-cockpit-recommendations` | Underutilized GCE / host CPU |
| `gcp-cockpit-storage-recommendations.yaml` | `gcp-cockpit-recommendations` | Large GCS buckets with observed storage but no observed API requests |
| `gcp-cockpit-loadbalancing-recommendations.yaml` | `gcp-cockpit-recommendations` | HTTP(S) load balancers with observed request metrics but no requests |
| `gcp-cockpit-pubsub-recommendations.yaml` | `gcp-cockpit-recommendations` | Pub/Sub subscription backlog or oldest-message age |
| `gcp-cockpit-assets.yaml` | `gcp-cockpit-assets` | Live GCE/GCS inventory from metrics |
| `gcp-cockpit-coverage.yaml` | `gcp-cockpit-coverage` | Per-dataset coverage rows (supplemental) |

Storage and load-balancing workflows deploy automatically because their metric
inputs are always enabled. The Pub/Sub workflow deploys only when
`enable_pubsub_metrics = true`. Every recommendation workflow deletes only its
own `resource.type` snapshot, uses stable resource keys and document IDs, and
bounds ES|QL results and fanout to 200 resources.

## Explicit unsupported / unknown gaps

No recommendation workflow is provided for BigQuery, Service Health, or
Cloud Functions. The configured integration currently has no real dataset
contract for those services, so their telemetry and recommendation state
remain **unsupported / unknown**. Dataset absence must not be interpreted as
healthy, inactive, or unused; add a workflow only after a concrete metric or
log contract is configured and tested.

## Cross-project seeder (Security → Observability)

CPS qualifiers from Observability currently raise `no_matching_project_exception`
even when the Cloud link is `enabled`. Terraform therefore runs:

```bash
python3 modules/cockpit-dashboard/scripts/seed_gcp_insight_indices.py \
  --obs-es "$OBS_ES" --sec-es "$SEC_ES" \
  --obs-password "$OBS_PASSWORD" --sec-password "$SEC_PASSWORD"
```

on apply (`terraform_data.seed_gcp_insight_indices`). It mirrors:

| Index | Contents |
| --- | --- |
| `gcp-cockpit-security-kpi` | active / high-critical alerts, CSPM, audit, firewall counts |
| `gcp-cockpit-coverage` | service tile health (Compute, GKE, Storage, Audit, …) |
| `gcp-cockpit-assets` | GCE + GCS inventory |
| `gcp-cockpit-events` | Audit / firewall highlights + recommendation churn |

Triggers: workflows = manual + scheduled every `1h`. Seeder = every apply
(and safe to cron hourly).

## Re-export / refresh from live Kibana

```bash
../../scripts/export-kibana-workflows.sh \
  --kibana "$OBS_KIBANA" --user admin --password "$OBS_PASSWORD" \
  --out .
```
