# Azure Observe and Protect (modern PoC)

Creates Elastic Cloud Serverless Security Complete (or hosted), Azure Event Hub + subscription diagnostics, a dedicated app registration for Elastic, Fleet integrations (`azure`, `azure_metrics`, `azure_billing`, optional agentless CSPM), and Azure-tagged detection rules.

## Prerequisites

```bash
export EC_API_KEY="..."
# Provide Azure SP used by Terraform itself via tfvars or env:
# ARM_CLIENT_ID / ARM_CLIENT_SECRET / ARM_SUBSCRIPTION_ID / ARM_TENANT_ID
```

```bash
cd examples/azure
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform apply
```
