# Google Cloud Observe and Protect (modern PoC)

Creates:

1. **Elastic Security** serverless project (Complete) — Fleet, GCP Pub/Sub integrations, agentless CSPM, detection rules, GCE Elastic Agent
2. **Elastic Observability** serverless project (Complete) — linked to Security via **Cross-Project Search**
3. **Cockpit dashboard** on Observability — aggregated alerts, data-flow health, ML/AI agent posture, GCP inventory
4. GCP Pub/Sub topics + logging sinks, collector SA, company-policy labels

## Company labels (required)

Every labelable GCP resource gets your policy labels via `company_labels`. Values are normalized to GCP rules (lowercase, `[a-z0-9_-]`). Compute instances require a valid `division` label for org-policy constrained projects.

```hcl
company_labels = {
  division    = "field"
  cost-center = "platform"
  owner       = "sre-team"
  environment = "poc"
}
```

## Prerequisites

Terraform credentials need permission to create Compute Engine instances (Elastic Agent VM), Pub/Sub, Logging sinks, and IAM bindings.

```bash
export EC_API_KEY="..."
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa.json
```

```bash
cd examples/gcp
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform apply
```

## What to open after apply

| Surface | Where |
| --- | --- |
| Cockpit dashboard | `observability_kibana_url` → Dashboards → **GCP Observe & Protect Cockpit** (or `cockpit_dashboard_url`) |
| Security / Fleet / CSPM | `kibana_url` |
| AI agents | Observability → Agent Builder (`gcp-security-analyst`, `gcp-obs-triage`) |

Toggle Observability hub with `enable_observability_project = false` if you only want Security.
