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

## Enrolling an agent (optional)

Agentless CSPM and many metrics work without a host agent. For S3/SQS log inputs (CloudTrail, etc.) and Event Hub / Pub/Sub log inputs, enroll Elastic Agent into the created Fleet policy using the `enrollment_token` and `kibana_url` outputs:

```bash
sudo elastic-agent install \
  --url=<fleet-or-kibana-url> \
  --enrollment-token=<enrollment_token>
```

## Modules

| Module | Role |
|---|---|
| `modules/elastic-project` | `ec_security_project` or `ec_deployment` |
| `modules/elastic-stack` | Fleet policies, integrations, managed/agentless, detection rules |
| `modules/aws-cloud` | S3, SQS, CloudTrail, VPC flow logs, collector IAM role |
| `modules/azure-cloud` | Event Hub, diagnostics, app registration |
| `modules/gcp-cloud` | Pub/Sub topics, logging sinks, collector SA |

## Legacy layout

The original `AWS/`, `Azure/`, `GoogleCloud/`, `MultiCloud/`, `AWS-agents/`, `Monitoring/`, `Kubernetes/`, and `lib/` trees are **deprecated**. They pin old `elastic/ec` versions and drive Fleet via shell scripts. Prefer `examples/` + `modules/`.
