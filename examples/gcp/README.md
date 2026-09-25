# Google Cloud Observe and Protect (modern PoC)

Creates Elastic Cloud Serverless Security Complete (or hosted), Pub/Sub topics + logging sinks (audit, firewall, VPC flow, DNS, LB), a collector service account, Fleet GCP integration at latest version, a GCE Elastic Agent enrolled into that policy, optional agentless CSPM, and GCP-tagged detection rules.

## Company labels (required)

Every labelable GCP resource gets your policy labels via `company_labels`. Values are normalized to GCP rules (lowercase, `[a-z0-9_-]`).

```hcl
company_labels = {
  cost-center = "platform"
  owner       = "sre-team"
  environment = "poc"
}

# Optional: fail terraform plan if keys are missing
required_label_keys = ["cost-center", "owner", "environment"]
```

## Prerequisites

Terraform credentials need permission to create Compute Engine instances (for the Elastic Agent VM), Pub/Sub, Logging sinks, and IAM bindings — e.g. `roles/compute.instanceAdmin.v1` in addition to Pub/Sub/Logging roles.

```bash
export EC_API_KEY="..."
# ADC or credentials file for Terraform
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa.json
```

```bash
cd examples/gcp
cp terraform.tfvars.example terraform.tfvars
# edit company_labels + google_cloud_project
terraform init
terraform apply
```

After apply, open Fleet → Agents and confirm the GCE agent is Healthy. Pub/Sub log and metrics streams require that agent; CSPM remains agentless.
