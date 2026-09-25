# AWS Observe and Protect (modern PoC)

Mirrors the GCP dual-project pattern for AWS:

1. **Elastic Security** serverless (Complete) — agentless CSPM (+ optional CNVM), agent CloudTrail, AWS detection rules
2. **Elastic Observability** serverless — CPS-linked hub with agent vpcflow + CloudWatch/EC2/S3/billing metrics
3. **Cockpit dashboard** on Observability — pinned NDJSON (`modules/cockpit-dashboard/cockpit-aws.ndjson`)
4. **Kibana Workflows** — YAML under `examples/aws/workflows/` (optional execute-on-apply)

## Agentless vs agent

| Integration | Mode | Why |
| --- | --- | --- |
| CSPM (CIS AWS) | **Agentless** | `cloud_security_posture` managed integration |
| CNVM / vuln_mgmt | **Agentless** | same package, `vuln_mgmt` policy template |
| CloudTrail | **Agent** | S3/SQS package input not available agentless |
| VPC Flow Logs | **Agent** | S3/SQS package input not available agentless |
| CloudWatch / EC2 / S3 / billing metrics | **Agent** | AWS metrics streams require Elastic Agent |

Two EC2 Elastic Agents enroll into the Security and Observability Fleet policies respectively. No static AWS access keys are embedded; collection uses IAM assume-role + external id.

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
