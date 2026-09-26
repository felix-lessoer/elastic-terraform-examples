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
| `gcp-cockpit-assets.yaml` | `gcp-cockpit-assets` | Live GCE/GCS inventory from metrics |
| `gcp-cockpit-coverage.yaml` | `gcp-cockpit-coverage` | Per-dataset coverage rows (supplemental) |

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
