# Getting started — Elastic multi-cloud PoC (modern)

Stand up an Elastic **Security Complete** environment and the cloud collectors needed for a strong observe-and-protect demo — typically in minutes after credentials are ready.

## What you get

1. Elastic Cloud **Serverless** Security project (Complete tier) — or hosted fallback
2. CSP plumbing (AWS CloudTrail→S3→SQS + IAM role, Azure Event Hub + diagnostics, GCP Pub/Sub sinks)
3. Fleet integrations at **latest** package versions via `elastic/elasticstack` (no curl scripts)
4. Agentless **CSPM** where supported
5. Prebuilt detection rules installed and CSP-tagged rules enabled
6. Optional multi-cloud **Cross-Project Search** (Serverless) or CCS (hosted)

## Prerequisites

| Tool | Notes |
|---|---|
| Terraform | **>= 1.2.7** |
| Elastic Cloud API key | `export EC_API_KEY=...` |
| CSP credentials | AWS / Azure / GCP as required by the example you run |

## Choose an entry point

| Path | Use when |
|---|---|
| [`examples/aws`](../examples/aws) | AWS-only PoC (reference implementation) |
| [`examples/azure`](../examples/azure) | Azure-only PoC |
| [`examples/gcp`](../examples/gcp) | GCP-only PoC |
| [`examples/multicloud`](../examples/multicloud) | One or more clouds + CPS/CCS hub |

```bash
cd examples/aws
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform apply
```

Open the `kibana_url` output. CSPM findings, integration dashboards, and Security rules should populate as data arrives.

## Defaults (PoC-friendly)

- `deployment_mode = "serverless"`
- `product_tier = "complete"` (required for Cross-Project Search)
- `enable_cspm = true`
- `enable_detection_rules = true`
- AWS IAM **assume_role + external id** (no static keys in Fleet policies)
- Latest Fleet package versions via `data.elasticstack_fleet_integration`
- **Company tags/labels are required** — set `company_labels` (GCP) or `company_tags` (AWS/Azure/multicloud)

### Company tagging

```hcl
# examples/gcp
company_labels = {
  cost-center = "platform"
  owner       = "sre-team"
  environment = "poc"
}
required_label_keys = ["cost-center", "owner", "environment"]  # optional guardrail
```

Labels are normalized for GCP / Elastic Cloud metadata rules and applied to Pub/Sub topics, subscriptions, and (sanitized) to the Elastic project.

## Enrolling an agent

- **GCP (`examples/gcp`)**: by default Terraform deploys a GCE VM (`enable_elastic_agent = true`) that enrolls into the Fleet policy automatically.
- **AWS / Azure / multicloud**: Agentless CSPM works without a host agent. For S3/SQS, Event Hub, or Pub/Sub log inputs, enroll Elastic Agent into the created Fleet policy:

```bash
sudo elastic-agent install \
  --url=<fleet_url> \
  --enrollment-token=<enrollment_token> \
  --force --non-interactive
```

Use the `fleet_url` / `enrollment_token` outputs from the example.
## Modules

| Module | Role |
|---|---|
| `modules/elastic-project` | `ec_security_project` or `ec_deployment` |
| `modules/elastic-stack` | Fleet policies, integrations, managed/agentless, detection rules |
| `modules/elastic-agent-gce` | GCE VM that installs and enrolls Elastic Agent |
| `modules/aws-cloud` | S3, SQS, CloudTrail, VPC flow logs, collector IAM role |
| `modules/azure-cloud` | Event Hub, diagnostics, app registration |
| `modules/gcp-cloud` | Pub/Sub topics, logging sinks, collector SA |

## Legacy layout

The original `AWS/`, `Azure/`, `GoogleCloud/`, `MultiCloud/`, `AWS-agents/`, `Monitoring/`, `Kubernetes/`, and `lib/` trees are **deprecated**. They pin old `elastic/ec` versions and drive Fleet via shell scripts. Prefer `examples/` + `modules/`.
