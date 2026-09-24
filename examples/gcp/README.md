# Google Cloud Observe and Protect (modern PoC)

Creates Elastic Cloud Serverless Security Complete (or hosted), Pub/Sub topics + logging sinks (audit, firewall, VPC flow, DNS, LB), a collector service account, Fleet GCP integration at latest version, optional agentless CSPM, and GCP-tagged detection rules.

## Prerequisites

```bash
export EC_API_KEY="..."
# ADC or credentials file for Terraform
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa.json
```

```bash
cd examples/gcp
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform apply
```
