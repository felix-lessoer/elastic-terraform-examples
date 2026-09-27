# Pinned Kibana Workflow YAML — AWS cockpit insight fabric

These workflows (plus the cross-project seeder) power Datadog-comparable
insights on the Observability cockpit. Filenames are stable `workflow_id`s
deployed by `module.workflows_obs`.

| File | Writes to | Purpose |
| --- | --- | --- |
| `aws-cockpit-ec2-recommendations.yaml` | `aws-cockpit-recommendations` | EC2 underutilized / hot CPU + failed status checks |
| `aws-cockpit-s3-recommendations.yaml` | `aws-cockpit-recommendations` | Empty / near-empty S3 buckets |
| `aws-cockpit-assets.yaml` | `aws-cockpit-assets` | Live EC2/S3 inventory from metrics |
| `aws-cockpit-coverage.yaml` | `aws-cockpit-coverage` | Per-dataset coverage rows (supplemental) |

## Cross-project seeder (Security → Observability)

CPS qualifiers from Observability currently raise `no_matching_project_exception`
even when the Cloud link is `enabled`. Terraform therefore runs:

```bash
python3 modules/cockpit-dashboard/scripts/seed_aws_insight_indices.py \
  --obs-es "$OBS_ES" --sec-es "$SEC_ES" \
  --obs-password "$OBS_PASSWORD" --sec-password "$SEC_PASSWORD"
```

on apply (`terraform_data.seed_aws_insight_indices`). It mirrors:

| Index | Contents |
| --- | --- |
| `aws-cockpit-security-kpi` | active / high-critical alerts, CSPM, CloudTrail, Health counts |
| `aws-cockpit-coverage` | service tile health (EC2, S3, VPC Flow, CloudTrail, …) |
| `aws-cockpit-assets` | EC2 + S3 inventory |
| `aws-cockpit-health` | mirrored AWS Health events (Security → Observability) |
| `aws-cockpit-events` | AWS Health + CloudTrail highlights + recommendation churn |

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
python3 ../../modules/cockpit-dashboard/scripts/generate_aws_recommendations.py \
  --es-url "$AWS_OBS_ES" --password "$OBS_PASSWORD"
python3 ../../modules/cockpit-dashboard/scripts/seed_aws_insight_indices.py \
  --obs-es "$AWS_OBS_ES" --sec-es "$AWS_SEC_ES" \
  --obs-password "$OBS_PASSWORD" --sec-password "$SEC_PASSWORD"
```
