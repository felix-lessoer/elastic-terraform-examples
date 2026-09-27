# Elastic AWS PoC Guide

A local React application built with Elastic UI (EUI) that guides an operator
through the AWS Terraform deployment in `examples/aws`.

It is intentionally a local application rather than a Kibana plugin. Elastic
Cloud Serverless does not support custom Kibana plugins, and keeping the server
on the Terraform workstation allows it to reuse the operator's existing AWS,
Terraform, Python, and Elastic credentials without sending them to a browser or
hosted service.

## Responsibilities

The UI can:

- write a non-secret `*.auto.tfvars.json` configuration;
- validate local tools, AWS identity, and presence of `EC_API_KEY`;
- run `terraform init`;
- create and display a saved Terraform plan;
- apply only that saved plan after an explicit confirmation;
- trigger only the Kibana Workflows reported by Terraform outputs;
- stream local execution logs; and
- link to the deployed AWS cockpit and Elastic project.

It does not:

- create an example application;
- accept AWS or Elastic secrets through browser fields;
- provide an arbitrary command shell;
- expose Terraform's sensitive outputs to the browser;
- bind to a non-loopback interface; or
- approve workload instrumentation.

## Prerequisites

- Node.js 22 or later
- Terraform
- Python 3
- AWS CLI with the intended customer identity
- `EC_API_KEY` exported in the shell that starts the local server

Use the same credential provider chain that would be used when running
Terraform directly:

```bash
export EC_API_KEY="..."
export AWS_PROFILE="customer-poc"
export AWS_REGION="eu-west-1"
```

Do not put credentials in the generated Terraform variable file.

## Run

From the repository root:

```bash
cd tools/aws-poc-ui
npm ci
npm run build
npm start
```

Open <http://127.0.0.1:5602>.

For UI development:

```bash
npm run dev
```

Vite runs on <http://127.0.0.1:5173> and proxies API requests to the local
server on port 5602.

## Local files

The guide creates these ignored files:

| File | Purpose |
| --- | --- |
| `examples/aws/aws-poc-ui.auto.tfvars.json` | Non-secret deployment configuration |
| `examples/aws/.aws-poc-ui.tfplan` | Saved plan reviewed before apply |

Execution logs are held in memory and disappear when the local server stops.
Known credential values are redacted before log lines are sent to the browser,
but operators should still treat Terraform logs as sensitive customer data.

## Security model

- The server binds only to `127.0.0.1`.
- Browser mutations require an in-memory CSRF token.
- Browser origins are restricted to `localhost` and `127.0.0.1`.
- Commands and arguments are fixed server-side and run without a shell.
- Only an allow-list of non-sensitive Terraform outputs reaches the browser.
- Kibana credentials are read from sensitive Terraform outputs only in the
  local server process.
- Workflow IDs must be both syntactically valid and present in Terraform's
  deployed `workflow_ids` output.

The workstation user is the trust boundary. Anyone who can control that user
or process can generally access the same AWS and Terraform credentials.

## Validation

```bash
npm test
npm run typecheck
npm run build
npm audit
```

## Future brownfield stages

The current UI exposes the steps that PR 12 implements today. As the brownfield
discovery work lands, add its deterministic Workflows to Terraform's
`workflow_ids` output. They will become triggerable without adding arbitrary
commands to the UI:

- inventory refresh;
- expected-versus-observed coverage;
- dependency rebuild;
- findings generation;
- instrumentation proposal; and
- approved canary validation.

Instrumentation approval must remain a separate human decision with a named
customer workload, exact change, expected cost, validation, and rollback.
