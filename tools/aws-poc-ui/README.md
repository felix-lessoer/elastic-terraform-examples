# Elastic PoC Deployment Creator

A local React application built with Elastic UI (EUI) that guides an operator
through the AWS Terraform deployment in `examples/aws`.

It is intentionally a local application rather than a Kibana plugin. Elastic
Cloud Serverless does not support custom Kibana plugins, and keeping the server
on the Terraform workstation allows it to reuse the operator's AWS, Terraform,
Python, and Elastic credentials without sending them to a hosted service.
Credentials entered in the browser travel only to the loopback server.

## Responsibilities

The UI can:

- write a non-secret `*.auto.tfvars.json` configuration;
- validate local tools, AWS identity, and presence of `EC_API_KEY`;
- run `terraform init`;
- create and display a saved Terraform plan;
- apply only that saved plan after an explicit confirmation;
- trigger only the Kibana Workflows reported by Terraform outputs;
- run bounded, read-only discovery of the existing AWS environment;
- derive local service candidates, dependencies, coverage, findings, and
  instrumentation proposals;
- stream local execution logs; and
- link to the deployed AWS cockpit and Elastic project.

Generated configuration always sets `deployment_creator_mode = true`. Direct
Terraform usage defaults this flag to `false`, retaining the existing required
company-tag behavior and excluding future UI-only resources.

It does not:

- create an example application;
- return saved AWS or Elastic secrets to the browser;
- provide an arbitrary command shell;
- expose Terraform's sensitive outputs to the browser;
- bind to a non-loopback interface; or
- approve workload instrumentation.

## Prerequisites

- Node.js 22 or later
- Terraform
- Python 3
- AWS CLI with the intended customer identity
- an Elastic Cloud API key
- an AWS shared profile or access/session credentials

`terraform` must be available on the `PATH` of the process that starts the UI.
Verify this with `terraform version`; the prerequisite step blocks initialization
and reports the missing executable when it is unavailable.

Credentials can be entered in the first UI step. They are saved to the ignored
`tools/aws-poc-ui/.env` file with mode `0600`, loaded immediately into the
local server process, and reused on later runs. Saved values are never returned
to the browser.

Alternatively, start the guide with the same environment that would be used
when running Terraform directly:

```bash
export EC_API_KEY="..."
export AWS_PROFILE="customer-poc"
export AWS_REGION="eu-west-1"
```

Environment values take precedence when the server starts. Do not put
credentials in the generated Terraform variable file.

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
| `tools/aws-poc-ui/.env` | Local Elastic and AWS credentials (`0600`) |
| `tools/aws-poc-ui/.elastic-poc/manifest.json` | Read-only AWS discovery result |
| `tools/aws-poc-ui/.elastic-poc/analysis.json` | Deterministic local analysis |
| `examples/aws/aws-poc-ui.auto.tfvars.json` | Non-secret deployment configuration |
| `examples/aws/.aws-poc-ui.tfplan` | Saved plan reviewed before apply |

Execution logs are held in memory and disappear when the local server stops.
Known credential values are redacted before log lines are sent to the browser,
but operators should still treat Terraform logs as sensitive customer data.

## Security model

- The server binds only to `127.0.0.1`.
- Browser mutations require an in-memory CSRF token.
- Browser origins are restricted to `localhost` and `127.0.0.1`.
- Saved credentials are written atomically with owner-only permissions.
- Credential status APIs return booleans and source metadata, never values.
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
python3 -m unittest discover -s python -p 'test_*.py'
```

## Local brownfield stages

The Deployment Creator can run these stages without Terraform changes:

- AWS inventory and configured-telemetry discovery;
- deterministic service candidate grouping;
- control-plane and existing X-Ray dependency inference;
- expected-versus-known telemetry coverage;
- health, ownership, and coverage findings; and
- descriptive instrumentation proposals.

The scripts use an explicit read-only AWS CLI operation allow-list, bounded API
calls, bounded resources per type, and partial-result reporting. They do not
enable telemetry, alter workloads, or write to Elastic.

Persisting the manifest and analysis into Elastic, scheduling recurring
refresh, expanding IAM roles, and implementing approved canary execution still
require Terraform changes.

Instrumentation approval must remain a separate human decision with a named
customer workload, exact change, expected cost, validation, and rollback.
