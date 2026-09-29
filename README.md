# Elastic Terraform — multi-cloud Observe and Protect

Provision an Elastic Cloud environment and the AWS / Azure / GCP collectors needed so **data flows and Security content understands the environment** — from nothing to a strong PoC in minutes.

> **Start here:** use the [PoC Builder UI](#quick-start-aws-poc-builder-ui)
> for an AWS PoC. The UI guides credentials, configuration, discovery,
> Terraform deployment, visibility expansion, and validation.

## Modern layout (use this)

```
modules/
  elastic-project/   # Serverless Security (default) or hosted ec_deployment
  elastic-stack/     # Fleet + integrations + detection rules (elasticstack provider)
  aws-cloud/         # Legacy modern AWS log plumbing used by multicloud
  azure-cloud/       # Event Hub, diagnostics, app registration
  gcp-cloud/         # Pub/Sub sinks + collector SA
examples/
  aws/               # One Observability project + one managed AWS collector
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
- The AWS entry point is intentionally **Observability-only**: one Serverless
  project, Elastic-managed integrations, and one EC2 Agent for integrations
  that do not support managed mode. Metrics cover all AWS regions; the pinned
  cockpit dashboard and Kibana workflow deployment are retained.

## Quick start: AWS PoC Builder UI

The **Elastic PoC Deployment Creator** is the recommended way to build an AWS
PoC. It runs locally on the Terraform workstation and guides the complete
process—do not run `terraform init`, `plan`, or `apply` separately.

### Prerequisites

- Node.js 22 or later
- Terraform
- Python 3
- AWS CLI
- an Elastic Cloud API key
- AWS credentials for the customer account

The AWS CLI and Terraform must be available on `PATH`. The UI preflight checks
all prerequisites before enabling deployment.

### Start the UI

From the repository root:

```bash
cd tools/aws-poc-ui
npm ci
npm run build
npm start
```

Open <http://127.0.0.1:5602> and keep the page open while operations run.

Enter the Elastic Cloud API key and AWS credentials in the first step, then
follow the guided workflow. The UI handles:

1. credential and local-tool validation;
2. AWS identity verification and PoC configuration;
3. Terraform initialization, plan creation, and a reviewable resource summary;
4. explicit approval and application of the saved plan;
5. read-only AWS discovery and service-gap analysis;
6. selection and deployment of approved visibility candidates;
7. Insight Engine workflow execution and validation; and
8. links to the deployed Elastic project and default AWS cockpit.

Credentials stay on the local workstation, and the server binds only to
`127.0.0.1`. For optional environment-variable startup, development mode, and
the full security model, see
[`tools/aws-poc-ui/README.md`](tools/aws-poc-ui/README.md).

Direct Terraform remains available for automation and advanced operators in
[`examples/aws/`](examples/aws/), but it is not the recommended PoC Quick Start.

## Legacy trees (deprecated)

`AWS/`, `AWS-agents/`, `Azure/`, `GoogleCloud/`, `MultiCloud/`, `Monitoring/`, `Kubernetes/`, and `lib/` remain for reference only. They target Elastic Stack ~8.4–8.5 era APIs and should not be used for new PoCs.

## License

See [LICENSE](LICENSE).
