# Pinned Kibana Workflow YAML — GCP cockpit recommendations

These workflows write into `gcp-cockpit-recommendations` for the cockpit
dashboard. Filenames are stable `workflow_id`s deployed by `module.workflows_obs`.

| File | Purpose |
| --- | --- |
| `gcp-cockpit-cloudrun-recommendations.yaml` | Cloud Run 5xx rate + idle instances |
| `gcp-cockpit-cloudsql-recommendations.yaml` | Cloud SQL high memory utilization |
| `gcp-cockpit-gke-recommendations.yaml` | Underutilized GKE nodes |
| `gcp-cockpit-host-recommendations.yaml` | Underutilized GCE / host CPU |

Triggers: manual + scheduled every `1h`. On apply, `execute_workflows_on_apply`
(default true) runs each enabled workflow once.

## Re-export / refresh from live Kibana

```bash
../../scripts/export-kibana-workflows.sh \
  --kibana "$OBS_KIBANA" --user admin --password "$OBS_PASSWORD" \
  --out .
```

If the workflows were deleted from Kibana but executions remain, regenerate via
Agent Builder (`platform.core.generate_workflow`) using the same workflow ids,
then replace the YAML files here.
