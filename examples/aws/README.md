# AWS Observe and Protect (modern PoC)

Mirrors the GCP dual-project pattern for AWS:

1. **Elastic Security** serverless (Complete) — agentless CSPM (+ optional CNVM), agent CloudTrail + console-home security, AWS detection rules
2. **Elastic Observability** serverless — CPS-linked hub with agent vpcflow + CloudWatch/EC2/S3/billing + Trusted Advisor metrics
3. **Cockpit dashboard** on Observability — pinned NDJSON (`modules/cockpit-dashboard/cockpit-aws.ndjson`)
4. **Kibana Workflows** — YAML under `examples/aws/workflows/` (optional execute-on-apply)

## Agentless vs agent

| Integration | Mode | Why |
| --- | --- | --- |
| CSPM (CIS AWS) | **Agentless** | `cloud_security_posture` managed integration |
| CNVM / vuln_mgmt | **Agentless** | same package, `vuln_mgmt` policy template |
| CloudTrail | **Agent** | S3/SQS package input not available agentless |
| Security Hub findings | **Agent** | httpjson streams; agentless available in package but this PoC uses IMDS on EC2 |
| GuardDuty findings | **Agent** | same pattern as Security Hub |
| AWS Health | **Agent** | `awshealth` metricset via agent IMDS |
| Trusted Advisor | **Agent** | CloudWatch `AWS/TrustedAdvisor` (no dedicated Elastic data stream) |
| VPC Flow Logs | **Agent** | S3/SQS package input not available agentless |
| CloudWatch / EC2 / S3 / billing metrics | **Agent** | AWS metrics streams require Elastic Agent |

Two EC2 Elastic Agents enroll into the Security and Observability Fleet policies. Agents use an **IAM instance profile** (IMDS) — no static AWS access keys in Fleet policies. Agentless CSPM/CNVM still assume the collector role with external id.

## Company tags (required)

Every taggable AWS resource gets your policy tags via `company_tags`, and the AWS provider also sets them as `default_tags`. Use the **same keys as GCP `company_labels`** — Elastic org SCPs deny creates (notably `sqs:CreateQueue`) when required tags are missing.

```hcl
company_tags = {
  division    = "field"
  org         = "sa"
  keep-until  = "2026-10-01"
  team        = "emea_central_area"
  project     = "felixroessel"
  environment = "poc"
}

required_tag_keys = [
  "division",
  "org",
  "keep-until",
  "team",
  "project",
  "environment",
]
```

## AWS console home → Elastic mapping

| Console widget | Elastic dataset(s) |
| --- | --- |
| Security findings | `logs-aws.securityhub_*`, `logs-aws.guardduty` |
| AWS Health | `metrics-aws.awshealth` |
| Trusted Advisor | `metrics-aws.cloudwatch_metrics` filtered to `AWS/TrustedAdvisor` (`RedResources`, `YellowResources`, `ServiceLimitUsage`) |

## Prerequisites

- Terraform >= 1.2.7
- `EC_API_KEY` for Elastic Cloud
- AWS credentials with permissions to create IAM, S3, SQS, CloudTrail, VPC Flow Logs, EC2

```bash
export EC_API_KEY="..."
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
# or use an AWS profile / SSO
```

## Apply

```bash
cd examples/aws
cp terraform.tfvars.example terraform.tfvars
# edit company_tags
terraform init
terraform apply
```

## Defaults

| Variable | Default | Notes |
| --- | --- | --- |
| `deployment_mode` | `serverless` | set `hosted` for classic `ec_deployment` |
| `product_tier` | `complete` | required for Cross-Project Search |
| `enable_cspm` | `true` | agentless CSPM |
| `enable_cnvm` | `true` | agentless vulnerability management |
| `enable_security_hub` | `true` | console Security findings |
| `enable_guardduty` | `true` | GuardDuty findings |
| `enable_aws_health` | `true` | console Health widget |
| `enable_trusted_advisor` | `true` | TA via CloudWatch metrics |
| `enable_billing_metrics` | `true` | agent-based Cost Explorer metrics |
| `enable_detection_rules` | `true` | tag `Data Source: AWS` |
| `enable_elastic_agent` | `true` | EC2 agents for non-agentless inputs |

## Surfaces

| Surface | Where |
| --- | --- |
| Cockpit dashboard | `observability_kibana_url` / `cockpit_dashboard_url` |
| Security Fleet / CSPM | `kibana_url` — agent `${name_prefix}-agent` |
| Observability Fleet | `observability_kibana_url` — agent `${name_prefix}-obs-agent` |
| AI agents | Observability → Agent Builder (`aws-security-analyst`, `aws-obs-triage`) |
| Kibana Workflows | YAML in `examples/aws/workflows/` |
