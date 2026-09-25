# Pinned Kibana Workflow YAML — AWS cockpit recommendations

These workflows write into `aws-cockpit-recommendations` for the cockpit
dashboard. Filenames are stable `workflow_id`s deployed by `module.workflows_obs`.

| File | Purpose |
| --- | --- |
| `aws-cockpit-ec2-recommendations.yaml` | EC2 underutilized / hot CPU + failed status checks |
| `aws-cockpit-s3-recommendations.yaml` | Empty / near-empty S3 buckets |

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
python3 ../../modules/cockpit-dashboard/scripts/generate_aws_recommendations.py \
  --es-url "$AWS_OBS_ES" --password "$OBS_PASSWORD"
```
