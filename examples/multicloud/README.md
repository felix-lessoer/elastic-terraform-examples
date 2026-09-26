# Multi-cloud Observe and Protect

Deploys one or more cloud observe/protect stacks and links them for **Cross-Project Search** (Serverless) or **CCS** (hosted).

## Quick start

```bash
export EC_API_KEY="..."
cd examples/multicloud
cp terraform.tfvars.example terraform.tfvars
# enable the clouds you have credentials for
terraform init
terraform apply
```

## Toggles

| Variable | Default | Description |
|---|---|---|
| `deploy_aws` | `true` | AWS Elastic project + CloudTrail/S3/SQS/IAM + Fleet |
| `deploy_azure` | `false` | Azure Elastic project + Event Hub + Fleet |
| `deploy_gcp` | `false` | GCP Elastic project + Pub/Sub sinks + Fleet |
| `cps_hub` | `aws` | Origin project for CPS / CCS |
| `deployment_mode` | `serverless` | `serverless` or `hosted` |
| `product_tier` | `complete` | Required for CPS |

The hub project links the other enabled projects automatically (`linked.projects` on Serverless, `remote_cluster` on hosted).
