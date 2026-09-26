# Pinned Kibana Workflow YAML — Azure cockpit insight fabric

These workflows (plus the cross-project seeder) power Datadog-comparable
insights on the Observability cockpit. Filenames are stable `workflow_id`s
deployed by `module.workflows_obs`.

| File | Writes to | Purpose |
| --- | --- | --- |
| `azure-cockpit-vm-recommendations.yaml` | `azure-cockpit-recommendations` | Underutilized / hot VM CPU |
| `azure-cockpit-storage-recommendations.yaml` | `azure-cockpit-recommendations` | Near-empty storage accounts |
| `azure-cockpit-assets.yaml` | `azure-cockpit-assets` | Live VM/storage inventory from metrics |
| `azure-cockpit-coverage.yaml` | `azure-cockpit-coverage` | Per-dataset coverage rows (supplemental) |

## Cross-project seeder (Security → Observability)

CPS qualifiers / placeholder aliases from Observability currently break hub
panels. Terraform therefore runs:

```bash
python3 modules/cockpit-dashboard/scripts/seed_azure_insight_indices.py \
  --obs-es "$OBS_ES" --sec-es "$SEC_ES" \
  --obs-password "$OBS_PASSWORD" --sec-password "$SEC_PASSWORD"
```

on apply (`terraform_data.seed_azure_insight_indices`). It mirrors:

| Index | Contents |
| --- | --- |
| `azure-cockpit-security-kpi` | active / high-critical alerts, CSPM, activity/platform log counts |
| `azure-cockpit-coverage` | service tile health (VM, Storage, Activity Logs, …) |
| `azure-cockpit-assets` | VM + storage account inventory |
| `azure-cockpit-events` | Activity log highlights + recommendation churn |

Triggers: workflows = manual + scheduled every `1h`. Seeder = every apply
(and safe to cron hourly).

## Re-export / refresh from live Kibana

```bash
../../scripts/export-kibana-workflows.sh \
  --kibana "$OBS_KIBANA" --user admin --password "$OBS_PASSWORD" \
  --out .
```

Offline backfill without workflows:

```bash
python3 ../../modules/cockpit-dashboard/scripts/generate_azure_recommendations.py \
  --es-url "$AZURE_OBS_ES" --password "$OBS_PASSWORD"
python3 ../../modules/cockpit-dashboard/scripts/seed_azure_insight_indices.py \
  --obs-es "$AZURE_OBS_ES" --sec-es "$AZURE_SEC_ES" \
  --obs-password "$OBS_PASSWORD" --sec-password "$SEC_PASSWORD"
```
