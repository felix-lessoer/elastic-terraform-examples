# Elastic Terraform — multi-cloud Observe and Protect

Provision an Elastic Cloud environment and the AWS / Azure / GCP collectors needed so **data flows and Security content understands the environment** — from nothing to a strong PoC in minutes.

> **Start here:** [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md) and the [`examples/`](examples/) folder.

## Modern layout (use this)

```
modules/
  elastic-project/   # Serverless Security (default) or hosted ec_deployment
  elastic-stack/     # Fleet + integrations + detection rules (elasticstack provider)
  aws-cloud/         # CloudTrail, S3, SQS, IAM assume-role
  azure-cloud/       # Event Hub, diagnostics, app registration
  gcp-cloud/         # Pub/Sub sinks + collector SA
examples/
  aws/               # AWS reference PoC
  azure/
  gcp/
  multicloud/        # Toggles + Cross-Project Search / CCS hub
docs/
  GETTING_STARTED.md
```

### Providers

| Provider | Version |
|---|---|
| `elastic/ec` | `~> 0.13` |
| `elastic/elasticstack` | `~> 0.16` |
| `hashicorp/aws` | `>= 5.0` |
| `hashicorp/azurerm` | `>= 3.100` |
| `hashicorp/google` | `>= 5.0` |

### Highlights vs the legacy examples

- **Serverless Security Complete** by default (`ec_security_project`), with hosted fallback
- Fleet agent policies / integrations / agentless CSPM via **Terraform state** (no `lib/elastic_api` curl scripts)
- Integration packages resolved to **latest** with `data.elasticstack_fleet_integration`
- Assume-role / app registration / service account credentials instead of static keys in policies
- Multi-cloud **Cross-Project Search** (Serverless) or CCS remotes (hosted)
- Elastic Serverless Forwarder / SAR path removed

## Quick start (AWS)

```bash
export EC_API_KEY="your-elastic-cloud-api-key"
cd examples/aws
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform apply
```

## Legacy trees (deprecated)

`AWS/`, `AWS-agents/`, `Azure/`, `GoogleCloud/`, `MultiCloud/`, `Monitoring/`, `Kubernetes/`, and `lib/` remain for reference only. They target Elastic Stack ~8.4–8.5 era APIs and should not be used for new PoCs.

## License

See [LICENSE](LICENSE).
