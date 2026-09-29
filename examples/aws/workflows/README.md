# Pinned Kibana Workflow YAML — AWS Insight Engine

These workflows turn raw AWS data into durable insights and an Agent Builder
briefing on the Observability cockpit. Filenames are stable `workflow_id`s.

| File | Writes to | Purpose |
| --- | --- | --- |
| `aws-cockpit-ec2-recommendations.yaml` | `aws-cockpit-recommendations` | EC2 utilization, status checks, and potentially unused instances |
| `aws-cockpit-s3-recommendations.yaml` | `aws-cockpit-recommendations` | Potentially unused empty S3 buckets |
| `aws-cockpit-lambda-insights.yaml` | `aws-cockpit-recommendations` | Lambda reliability, latency, and potentially unused functions |
| `aws-cockpit-rds-insights.yaml` | `aws-cockpit-recommendations` | RDS capacity pressure and potentially unused databases |
| `aws-cockpit-elb-insights.yaml` | `aws-cockpit-recommendations` | ALB reliability and potentially unused load balancers |
| `aws-cockpit-dynamodb-insights.yaml` | `aws-cockpit-recommendations` | DynamoDB reliability and potentially unused tables |
| `aws-cockpit-ecs-insights.yaml` | `aws-cockpit-recommendations` | ECS utilization, memory pressure, and potentially unused services |
| `aws-cockpit-ebs-insights.yaml` | `aws-cockpit-recommendations` | EBS performance and potentially unused volumes |
| `aws-cockpit-assets.yaml` | `aws-cockpit-assets` | Live EC2/S3 inventory from metrics |
| `aws-cockpit-coverage.yaml` | `aws-cockpit-dataset-coverage` | Per-dataset coverage rows (supplemental) |
| `aws-cockpit-insight-engine-summary.yaml` | `aws-cockpit-insight-summary` | Structured, prioritized summary from the `aws-recs-advisor` agent |

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
| `aws-cockpit-insight-summary` | Latest workflow-triggered Agent Builder briefing |

Triggers: workflows = manual + scheduled every `1h`. Seeder = every apply
(and safe to cron hourly).

Potentially unused findings require observed activity metrics throughout their
lookback window. Missing telemetry is left unknown, not classified as unused.

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
