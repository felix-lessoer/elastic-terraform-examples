# AWS Observe and Protect (modern PoC)

Creates an Elastic Cloud **Serverless Security Complete** project (or hosted fallback), AWS log plumbing (CloudTrail → S3 → SQS, IAM assume-role), agentless CSPM, AWS Fleet integrations at latest package versions, and enables AWS-tagged detection rules.

## Prerequisites

- Terraform >= 1.2.7
- `EC_API_KEY` for Elastic Cloud
- AWS credentials with permissions to create IAM, S3, SQS, CloudTrail, VPC Flow Logs

```bash
export EC_API_KEY="..."
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
# or use an AWS profile / SSO
```

## Apply

```bash
cd examples/aws
cp terraform.tfvars.example terraform.tfvars   # optional
terraform init
terraform apply
```

## Defaults

| Variable | Default | Notes |
|---|---|---|
| `deployment_mode` | `serverless` | set `hosted` for classic `ec_deployment` |
| `product_tier` | `complete` | required for Cross-Project Search |
| `enable_cspm` | `true` | agentless CSPM |
| `enable_detection_rules` | `true` | install + enable AWS-tagged rules |
| datasets | curated defaults | CloudWatch, billing, EC2, S3 metrics, CloudTrail |

No static AWS access keys are embedded in Fleet policies; collection uses an IAM role + external id.
