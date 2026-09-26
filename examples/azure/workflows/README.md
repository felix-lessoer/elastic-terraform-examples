# Pinned Kibana Workflow YAML — Azure cockpit recommendations

These workflows write into `azure-cockpit-recommendations` for the cockpit
dashboard. Filenames are stable `workflow_id`s deployed by `module.workflows_obs`.

| File | Purpose |
| --- | --- |
| `azure-cockpit-vm-recommendations.yaml` | Underutilized / hot VM CPU |
| `azure-cockpit-storage-recommendations.yaml` | Near-empty storage accounts |

Triggers: manual + scheduled every `1h`. On apply, `execute_workflows_on_apply`
(default true) runs each enabled workflow once.

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
```
