# AWS brownfield observability gap plan

**Purpose:** Extend the AWS PoC in PR 12 using the customer's existing workloads and telemetry.

**Baseline reviewed:** [PR 12](https://github.com/felix-lessoer/elastic-terraform-examples/pull/12) at `b91c89cdf2c968a91987af9b7a45a31e6c0740a1`

**Date:** 2026-09-27

## Product rule

The PoC must not deploy a sample application, synthetic monitored workload, traffic generator, or database merely to create something Elastic can observe.

It must:

1. inventory what already exists in the approved AWS accounts and Regions;
2. reuse telemetry the customer already produces;
3. infer resources, services, owners, dependencies, health, cost, and coverage with explicit evidence and confidence;
4. produce useful findings before application instrumentation;
5. detect the highest-value instrumentation opportunities automatically;
6. present an exact change, impact, cost, validation, and rollback plan;
7. modify an existing customer workload only after the customer approves that specific change.

This replaces the sample-service recommendations in the original gap analysis.

## Important technical constraint

AWS APIs can discover resources and configured relationships. Existing CloudWatch, X-Ray, OpenTelemetry, access-log, and VPC Flow data can reveal observed behavior. They cannot safely reveal every application process, framework, code path, or runtime dependency.

Elastic can automatically build a service map after traces exist. It cannot universally and safely inject APM into arbitrary EC2, ECS, EKS, and Lambda workloads without deployment-specific changes.

The defensible promise is:

> Discover automatically, infer where evidence permits, explain blind spots, and generate approval-ready instrumentation plans for real customer workloads.

It is not:

> Silently instrument every application without workload changes or restarts.

## What changes from the previous plan

| Previous proposal | Replacement |
|---|---|
| Deploy an OTel sample service or service chain | Detect existing customer services and rank them by PoC value and instrumentation feasibility |
| Generate a controlled application regression | Find actual anomalies, health events, changes, saturation, errors, or coverage gaps in customer data |
| Add a synthetic journey for the sample | Detect customer endpoints and existing synthetics; propose a check only with owner approval |
| Instrument a predefined Lambda chain | Discover existing Lambda event sources, destinations, layers, tracing, logs, and errors; propose one existing function as a canary |
| Instrument a sample database caller | Discover existing RDS and callers from traces, configuration, flows, and logs; use existing Performance Insights/logs where enabled |
| Calculate cost per request for the sample | Calculate resource/account/service costs immediately; calculate unit cost only when a real service has request or transaction telemetry |
| Make application instrumentation a P0 requirement | Make brownfield inventory, dependency evidence, and coverage scoring P0; instrumentation is an approved P1 action |

## Desired customer experience

After `terraform apply`, the customer should receive:

1. **Environment manifest:** accounts, Regions, resources, tags, owners, deployment systems, and telemetry sources.
2. **Service candidates:** grouped customer workloads such as ECS services, EKS workloads, Lambda functions, EC2/ASG applications, APIs, and databases.
3. **Dependency graph:** confirmed, probable, and candidate relationships with source evidence.
4. **Coverage matrix:** expected resources versus resources observed in metrics, logs, traces, profiles, and security data.
5. **Useful findings:** current health anomalies, stale alarms, error hotspots, expensive idle resources, missing owners, and telemetry blind spots.
6. **Instrumentation proposals:** ranked changes against named customer workloads, never generic advice.
7. **Agent-assisted investigation:** answers grounded in the manifest, telemetry, dependency evidence, and changes.

The initial report must still be useful when no application traces exist.

## Architecture

```text
Approved AWS accounts and Regions
  |
  +-- control-plane inventory
  |    Organizations, Resource Explorer, Config, Tagging API,
  |    EC2/ASG, ECS, EKS, Lambda, API Gateway, ELB, RDS,
  |    Cloud Map, CloudFormation/AppRegistry, SSM
  |
  +-- existing telemetry inventory
  |    CloudWatch metrics/logs/alarms, X-Ray, AMP/Prometheus,
  |    OTel/APM configuration, CloudTrail, VPC Flow Logs,
  |    ELB/API access logs, AWS Health
  |
  +-- Elastic collection already created by PR 12
       managed AWS integrations, EC2 Elastic Agent,
       existing S3/CloudWatch log discovery
             |
             v
  aws-cockpit-manifest
  aws-cockpit-service-candidates
  aws-cockpit-dependencies
  aws-cockpit-coverage
  aws-cockpit-findings
  aws-cockpit-instrumentation-plans
             |
             v
  Cockpit + ES|QL tools + Workflows + Brownfield Analyst agent
```

Terraform provisions the read-only access, Elastic resources, mappings, workflows, and tools. Discovery scripts query the customer environment and index normalized results. Workflows analyze indexed state and telemetry.

Do not add a continuously running discovery Lambda by default. It would add infrastructure and cost. The default refresh modes should be:

- during the initial apply;
- an explicit local refresh command using the same read-only AWS role;
- an optional scheduled mechanism only when the customer approves its resources and estimated cost.

Where Elastic Cloud Asset Discovery or an existing AWS Config aggregator already supplies inventory, consume it instead of duplicating collection.

## Phase 0 — Safety and scope contract

Add explicit variables and outputs before broadening discovery:

```hcl
discovery_account_ids
discovery_regions
discovery_resource_types
discovery_max_api_calls
discovery_metric_lookback_hours
discovery_logs_insights_scan_limit_bytes
enable_sensitive_configuration_discovery = false
enable_kubernetes_api_discovery         = false
enable_workload_mutation                = false
```

Required behavior:

- default to one approved account and enabled Regions;
- use read-only actions;
- never read secret values;
- redact environment-variable values by default;
- collect secret references only;
- classify every action as read-only, telemetry enablement, or workload mutation;
- estimate AWS and Elastic cost before enabling a new data source;
- snapshot any configuration that could later be changed;
- log API throttling, access denied, unsupported Region, and partial results;
- use two consecutive missing observations before marking a resource removed.

PR 12 currently enables GuardDuty, Security Hub, and Inspector during synchronization. Split that behavior from discovery and require an explicit flag because it mutates the customer environment and can incur cost.

## Phase 1 — Build an authoritative brownfield manifest

### Discovery order

Use existing aggregation services first to reduce API traffic:

1. AWS Organizations account/OU metadata when approved.
2. Existing AWS Resource Explorer aggregate view.
3. Existing AWS Config aggregator and advanced queries.
4. Resource Groups Tagging API for tags and supported resources.
5. Service-specific `List`, `Describe`, and `Get` APIs to fill gaps and obtain current relationships.

The Tagging API cannot be the only inventory source because it omits untagged and unsupported resources.

### Resource coverage

| Domain | Discover automatically |
|---|---|
| Account | account, OU, account tags, enabled Regions, delegated administrators |
| EC2/ASG | instances, state, AMI, instance type, ENIs, VPC/subnet, security groups, IAM profile, launch template, ASG, target groups |
| ECS | clusters, services, desired/running tasks, task definitions, images, ports, log drivers, service discovery, load balancers, deployment controller |
| EKS | clusters, versions, endpoint access, node groups, Fargate profiles, add-ons; Kubernetes workloads only after Kubernetes API approval |
| Lambda | functions, runtime, architecture, versions/aliases, layers, VPC, event-source mappings, destinations, DLQ, log group, tracing mode |
| API Gateway | APIs, stages, routes, integrations, domains, access-log and X-Ray configuration |
| ELB | load balancers, listeners, rules, target groups, targets, target health, access-log configuration |
| RDS/Aurora | instances/clusters, engine, topology, readers/writers, subnet/security groups, log exports, Enhanced Monitoring, Performance Insights |
| Messaging | SQS, SNS, EventBridge buses/rules/targets, Kinesis and MSK relationships |
| Deployment | CloudFormation stacks, AppRegistry applications, CodeDeploy/ECS deployment metadata where available |
| Telemetry | CloudWatch namespaces/alarms/log groups, X-Ray services, AMP workspaces, existing collector/exporter evidence |
| Ownership | owner/team/application/cost-center/repository tags, AppRegistry, stack metadata, alarm routes, deployment identities |

### Manifest schema

Store one document per resource in `aws-cockpit-manifest`:

```yaml
schema_version: 1
resource:
  arn: arn:aws:...
  type: aws.ecs.service
  name: checkout
  account_id: "123456789012"
  region: eu-west-1
  state: active
  tags: {}
  configuration_hash: "..."
grouping:
  service_candidate_id: "..."
  application_candidate: "..."
ownership:
  candidates:
    - value: payments
      source: tag.team
      confidence: 0.95
telemetry:
  metrics: observed
  logs: configured_not_observed
  traces: not_detected
  profiles: not_detected
  last_observed: "..."
evidence:
  - source: ecs.describe_services
    observed_at: "..."
```

Do not put the full manifest into Terraform state. The state would become large, stale, and potentially sensitive. Run discovery after Elastic is available, bulk index the results, and retain only a content hash and summary in Terraform outputs.

## Phase 2 — Detect existing observability before proposing anything

For each discovered resource, identify what the customer already has:

- CloudWatch metrics with recent datapoints;
- CloudWatch alarms and alarm history;
- log groups, retention, metric filters, and subscriptions;
- S3 access-log destinations;
- X-Ray tracing mode, service graph, sampled traces, and sampling rules;
- AMP workspaces and bounded Prometheus metadata/labels;
- existing OpenTelemetry collector/exporter configuration visible in ECS task definitions, EKS manifests, EC2 SSM inventory, Lambda layers, or environment-name metadata;
- existing Elastic APM agents and endpoints;
- supported third-party agents that must not be double-instrumented;
- VPC Flow Logs and access logs;
- deployment/change events in CloudTrail.

### Rules

- Reuse an existing OTLP/APM pipeline before proposing a new agent.
- Do not run EDOT and another APM agent in the same process.
- Do not assume an endpoint string proves that telemetry is flowing; verify recent documents.
- Do not read or index API keys, passwords, tokens, or environment-variable values.
- Do not enable all logs, detailed metrics, or tracing automatically.

### Lowest-touch opportunities

Rank these first:

1. existing Elastic APM already sending data;
2. existing OTel collector that can add an approved Elastic exporter;
3. existing X-Ray traces and service graph;
4. existing Prometheus/AMP telemetry;
5. existing service logs and access logs;
6. existing AWS metrics and alarms;
7. Cloud Asset Discovery and control-plane relationships.

## Phase 3 — Infer customer services and dependencies

### Service identity

Resolve a service candidate from the strongest available evidence:

1. `service.name` or existing APM/OTel/X-Ray identity;
2. AppRegistry or CloudFormation application;
3. ECS service/task family;
4. EKS namespace plus workload;
5. Lambda alias/function;
6. ASG or EC2 deployment group;
7. API Gateway domain/stage or ELB target-group membership;
8. conservative tag grouping.

Never group resources into an application only because they share a VPC, subnet, security group, or account.

### Dependency evidence

| Evidence | Example | Starting confidence |
|---|---|---:|
| Runtime trace | OTel/X-Ray parent and child spans | 0.98 |
| Explicit control-plane target | API Gateway integration, EventBridge target, Lambda event source | 0.95 |
| Routing configuration | ELB listener → target group → instance/task/IP | 0.95 |
| Orchestrator relationship | ECS service → task definition; EKS Service → EndpointSlice/pod | 0.92 |
| Repeated accepted flow | time-resolved ENI/IP VPC Flow records | 0.80 |
| Configured endpoint | sanitized host/service reference in task or workload configuration | 0.75 |
| Correlated request ID | access/application logs | 0.65 |
| Reachability only | compatible security groups/routes | 0.30 |
| Metric correlation | simultaneous request/CPU changes | 0.20 |

Store:

```yaml
from_resource: "..."
to_resource: "..."
relation: invokes
confidence: 0.95
classification: confirmed
first_seen: "..."
last_seen: "..."
evidence_refs: []
contradictory_evidence: []
```

Classification:

- **confirmed:** at least 0.90 or multiple independent high-quality sources;
- **probable:** 0.70–0.89;
- **candidate:** 0.45–0.69;
- **hidden by default:** below 0.45.

Metric correlation alone must never be presented as a dependency. Missing traces or flows are not negative evidence unless collection and sampling coverage are known.

## Phase 4 — Replace telemetry counts with expected-versus-observed coverage

PR 12 currently reports whether documents exist in selected datasets. Change coverage to answer:

- How many relevant resources did AWS discovery find?
- How many have fresh metrics?
- How many have useful logs?
- How many have traces or profiles?
- How many have an owner?
- How many have confirmed dependencies?
- Which missing signal prevents a specific investigation?

Example:

```yaml
service_type: aws.lambda.function
expected_resources: 84
metrics_observed: 84
logs_configured: 71
logs_fresh: 65
traces_observed: 9
owners_resolved: 52
high_value_gaps: 6
status: partial
```

Prioritize a gap using:

```text
value score =
  production criticality
  × active health/error evidence
  × traffic/activity
  × dependency centrality
  × investigation value
  × instrumentation feasibility
  ÷ estimated risk and cost
```

The result should say "six active production Lambda functions with elevated errors have no traces", not "Lambda APM is missing".

## Phase 5 — Produce useful outcomes without APM

The PoC must not wait for workload changes. Generate findings from existing customer data:

### Health and reliability

- unhealthy or flapping ELB targets;
- Lambda errors, throttles, duration, concurrency, and cold-start clues from existing logs;
- ECS desired-versus-running task gaps and failed deployments;
- EKS control-plane or node-group health where data exists;
- EC2 status checks and ASG capacity mismatch;
- RDS CPU, storage, connections, replica lag, failovers, and exported-log errors;
- SQS age/backlog and DLQ growth;
- API Gateway error and latency hotspots;
- AWS Health events mapped to affected resources.

### Change correlation

- CloudTrail changes preceding an anomaly;
- deployments, task-definition changes, Lambda versions, ASG launch-template changes, RDS modifications, and security-group changes;
- alarm-state transitions correlated with those changes.

Call these correlated changes, not proven root causes, unless stronger runtime evidence exists.

### Cost and waste

- stopped/idle/underused EC2 and unattached EBS;
- NAT Gateway traffic/cost hotspots;
- idle load balancers;
- overprovisioned ECS services when utilization evidence supports it;
- Lambda memory/duration opportunities;
- RDS rightsizing candidates with performance safeguards;
- S3 lifecycle/storage-class opportunities;
- unowned resources and missing allocation tags.

### Coverage and governance

- resources without owners;
- production services without alarms;
- active resources without fresh telemetry;
- log groups with unbounded retention;
- existing telemetry that is not collected by Elastic;
- duplicate agents/collectors or conflicting instrumentation.

Every finding must include evidence, affected resources, confidence, expected value, and a next action.

## Phase 6 — Generate plans for existing customer workloads

The system should create a plan document, not execute instrumentation.

```yaml
plan_id: "..."
target:
  arn: "..."
  service_candidate: "..."
reason:
  finding_ids: []
  blocked_investigations: []
current_state:
  deployment_type: ecs
  task_definition_revision: 41
  telemetry: {}
proposal:
  method: existing_otel_exporter
  exact_changes: []
  required_permissions: []
  restart_or_replacement: true
  estimated_aws_cost: "..."
  estimated_elastic_volume: "..."
validation:
  health_checks: []
  success_criteria: []
rollback:
  task_definition_revision: 41
status: draft
```

### Instrumentation feasibility by workload

| Existing workload | Automatic discovery | Preferred proposal | Change/restart reality |
|---|---|---|---|
| Existing OTel | Detect collector/exporter evidence and verify telemetry | Add or redirect an exporter to Elastic | Collector reload/restart may be required |
| Existing Elastic APM | Detect recent APM telemetry | Keep it; avoid reinstrumentation | Usually no change |
| EC2 application | Discover EC2/ASG, SSM state, ports, logs, runtime clues | Host metrics/logs first; runtime-specific EDOT/APM only for a named process | APM usually requires service restart; Java attach is a narrow exception |
| ECS on EC2 | Discover service/task definition/log driver/targets | Existing collector, daemon collector, then runtime agent if justified | Task-definition change replaces tasks |
| ECS Fargate | Discover task/service configuration | Direct OTLP or collector/sidecar plan | Task-definition change replaces tasks; no host/eBPF access |
| EKS | Discover cluster; workloads after API approval | Cluster collector first; operator injection only on selected workload/namespace | Injection recreates pods; Fargate coverage is partial |
| Lambda | Discover runtime/layers/tracing/logs/errors | Elastic/OTel layer and extension for one named function/version | Configuration changes recycle environments; use alias/version rollback |
| API Gateway/ELB | Discover stages/listeners/targets/log settings | Enable selected access logs or tracing only when needed | No app restart, but configuration and cost change |
| RDS | Discover engine/topology/monitoring/log exports | Use existing metrics/logs/Performance Insights; trace callers | Caller instrumentation is needed for application DB spans |

Any proposed mutation must identify the workload owner, maintenance window, canary scope, expected overhead, and rollback target.

## Phase 7 — Approval and canary validation

Separate planning from execution:

1. Agent or Workflow creates a draft proposal.
2. Customer reviews exact diff, permissions, cost, restart, validation, and rollback.
3. Customer approves a named workload and change ID.
4. Existing customer deployment tooling applies the change whenever possible.
5. Elastic validates pre/post error rate, latency, CPU, memory, restarts, and telemetry volume.
6. Expansion requires a separate decision.
7. Roll back automatically only if the customer explicitly authorizes that behavior; otherwise alert and present the rollback command.

Do not give an AI agent a generic AWS write credential. If direct automation is later enabled, expose only narrow allow-listed Workflows that require approval and verify the target ARN/change ID.

## Workflows

Create these Workflows:

| Workflow | Trigger | Behavior |
|---|---|---|
| `aws-brownfield-inventory-refresh` | manual; optional schedule | Run or ingest a read-only discovery snapshot, upsert resources, and mark stale resources |
| `aws-brownfield-telemetry-coverage` | after inventory; hourly | Join manifest to recent Elastic datasets and calculate expected-versus-observed coverage |
| `aws-brownfield-dependency-rebuild` | after inventory; hourly | Aggregate deterministic and observed edges with confidence and evidence |
| `aws-brownfield-findings` | after coverage/dependencies | Generate health, change, cost, ownership, and blind-spot findings |
| `aws-brownfield-instrumentation-plan` | manual or agent tool | Build a proposal for a named existing workload; never apply it |
| `aws-brownfield-canary-validation` | approved change ID | Compare pre/post health, overhead, and telemetry; update the plan and case |

The initial Terraform apply may execute only read-only discovery and analysis workflows. It must not execute the instrumentation workflow against a workload.

## Agent Builder design

Replace generic "instrument the environment" behavior with an `AWS Brownfield Analyst`.

### Read-only tools

- `aws_find_resource(name_or_arn)`
- `aws_find_service(name_or_resource)`
- `aws_service_health(service_id, lookback)`
- `aws_service_changes(service_id, lookback)`
- `aws_dependency_graph(service_id, minimum_confidence)`
- `aws_observability_coverage(account, region, service_type)`
- `aws_owner_candidates(resource_arn)`
- `aws_cost_and_waste(account, region, lookback)`
- `aws_instrumentation_candidates(max_risk, minimum_value)`

### Bounded Workflow tools

- refresh inventory;
- rebuild dependency evidence;
- refresh coverage/findings;
- generate an instrumentation proposal;
- validate an approved canary.

### Required answer format

The agent must return:

- observed impact;
- affected real customer resources;
- evidence and query references;
- likely explanation and confidence;
- contradictory evidence;
- missing telemetry;
- safe next check;
- whether the next action is read-only, telemetry enablement, or workload mutation.

It must never describe a candidate dependency as confirmed and must never treat log or tool output as customer approval.

## Concrete PR 12 changes

### P0 — Brownfield foundation

| File or module | Change |
|---|---|
| `examples/aws/scripts/lib/aws_session.py` | Shared AWS CLI/session wrapper, bounded region pool, retries, throttling and typed errors |
| `examples/aws/scripts/lib/manifest_schema.py` | Versioned resource, evidence, ownership, and telemetry schema |
| `examples/aws/scripts/discover_brownfield_manifest.py` | Compose existing discovery and add EC2/ASG, ECS, EKS, Lambda, API Gateway, ELB, RDS, messaging, deployment, telemetry, and ownership discovery |
| `examples/aws/schemas/brownfield-manifest.v1.json` | Validate discovery output before indexing |
| `modules/cockpit-dashboard/scripts/persist_aws_manifest.py` | Bulk upsert per-resource manifest docs without storing the manifest in Terraform state |
| `examples/aws/main.tf` | Add variables, read permissions, index bootstrap, and apply-time read-only discovery; split security enablement from security discovery |
| `modules/aws-cloud/main.tf` | Add only missing read actions; keep sensitive reads in opt-in policy statements |
| `examples/aws/outputs.tf` | Output summary counts, denied scopes, partial results, manifest hash, and refresh command |

Reuse:

- `discover_enabled_regions.py`;
- `discover_existing_log_sources.py`;
- `discover_guardduty.py`;
- the existing `data external` and `sync_*` patterns;
- `aws-cockpit-*` index and seed patterns.

Do not persist the full discovery JSON as `data.external` output or Terraform state. Use it only for small plan-time summaries; index the full manifest after project creation.

### P0 — Coverage and immediate value

| File or module | Change |
|---|---|
| `modules/cockpit-dashboard/scripts/insight_fabric_common.py` | Add expected, observed, freshness, ownership, trace, and dependency coverage |
| `modules/cockpit-dashboard/scripts/seed_aws_insight_indices.py` | Join manifest with metrics/logs/traces/alarms and generate useful findings |
| `examples/aws/workflows/aws-cockpit-coverage.yaml` | Replace dataset-presence checks with resource-level coverage |
| `examples/aws/workflows/aws-brownfield-findings.yaml` | Generate health, change, cost, ownership, and blind-spot findings |
| `modules/cockpit-dashboard/scripts/inject_aws_insight_panels.py` | Add discovered services, dependency confidence, coverage, and findings panels |

### P1 — Dependencies and plans

| File or module | Change |
|---|---|
| `modules/cockpit-dashboard/scripts/infer_aws_dependencies.py` | Build evidence-backed edges from AWS configuration and existing telemetry |
| `examples/aws/workflows/aws-cockpit-dependencies.yaml` | Refresh graph documents |
| `examples/aws/scripts/build_instrumentation_plans.py` | Rank real workload candidates and generate exact dry-run plans |
| `examples/aws/workflows/aws-brownfield-instrumentation-plan.yaml` | Generate plan only |
| `examples/aws/workflows/aws-brownfield-canary-validation.yaml` | Validate an externally applied, approved change |
| `modules/observability-seed/main.tf` | Add manifest, dependencies, findings, and plan tools; update agent instructions |
| `examples/aws/agent_workflow_tools.tf` | Expose only bounded refresh, plan, and validation workflows |
| `examples/aws/main.tf` | Pass approved workflow tool IDs to the agents and enforce creation order |

## Implementation order

1. Separate read-only discovery from AWS service enablement.
2. Extract common AWS/Fleet script helpers.
3. Build and validate the resource manifest.
4. Index the manifest and expose collection errors.
5. Change coverage to expected resources versus observed telemetry.
6. Generate immediate health, change, cost, ownership, and coverage findings.
7. Infer deterministic dependencies from AWS configuration.
8. Add observed edges from existing traces, flows, and access logs.
9. Add Brownfield Analyst tools.
10. Generate instrumentation proposals for real workloads.
11. Add approved canary validation.
12. Only then implement optional mutation workflows.

## Acceptance criteria

### No-mutation deployment

- creates no sample workload or traffic;
- performs no application, task, pod, function, database, gateway, or load-balancer mutation;
- does not enable paid AWS security or telemetry services unless explicitly selected;
- inventories approved resources with partial-result reporting;
- produces useful findings from existing metrics, logs, alarms, configuration, and changes;
- reports exact blind spots rather than treating absent data as healthy.

### Dependency quality

- every displayed edge has evidence and confidence;
- deterministic AWS relationships and observed runtime relationships are distinguishable;
- metric correlation alone never creates a confirmed edge;
- stale IP/ENI mappings are time-resolved;
- the UI can hide low-confidence candidates.

### Instrumentation proposals

- every proposal targets an existing ARN/workload;
- detects conflicting/existing instrumentation;
- includes owner, value, exact change, permissions, restart, cost, success criteria, and rollback;
- cannot apply without a specific approval;
- uses the customer's deployment mechanism where possible.

### PoC success

- time from apply to environment manifest;
- percentage of discovered resources with fresh metrics/logs/traces/owners;
- number of useful findings before workload instrumentation;
- percentage of dependency edges backed by deterministic or runtime evidence;
- time from a real alert/finding to affected resource, owner, recent change, and dependency;
- instrumentation coverage gained per approved change;
- measured overhead and ingest cost of each canary;
- complete removal/rollback inventory at PoC exit.

## Source references

### AWS discovery and evidence

- [AWS Config advanced queries](https://docs.aws.amazon.com/config/latest/developerguide/querying-AWS-resources.html)
- [AWS Resource Explorer with Organizations](https://docs.aws.amazon.com/organizations/latest/userguide/services-that-can-integrate-resource-explorer.html)
- [Resource Groups Tagging API GetResources](https://docs.aws.amazon.com/resourcegroupstagging/latest/APIReference/API_GetResources.html)
- [CloudWatch GetMetricData](https://docs.aws.amazon.com/AmazonCloudWatch/latest/APIReference/API_GetMetricData.html)
- [CloudWatch cross-account observability](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Unified-Cross-Account.html)
- [X-Ray GetServiceGraph](https://docs.aws.amazon.com/xray/latest/api/API_GetServiceGraph.html)
- [Amazon Managed Service for Prometheus query APIs](https://docs.aws.amazon.com/prometheus/latest/userguide/AMP-APIReference-Prometheus-Compatible-Apis.html)
- [VPC Flow Logs](https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs.html)
- [CloudTrail LookupEvents](https://docs.aws.amazon.com/awscloudtrail/latest/APIReference/API_LookupEvents.html)
- [IAM roles for third parties and ExternalId](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_common-scenarios_third-party.html)

### Elastic collection and instrumentation

- [Elastic AWS integration](https://www.elastic.co/docs/reference/integrations/aws)
- [AWS Cloud Asset Discovery](https://www.elastic.co/docs/solutions/security/cloud/asset-disc-aws)
- [Elastic Cloud Forwarder for AWS](https://www.elastic.co/docs/reference/opentelemetry/edot-cloud-forwarder/aws)
- [Elastic Cloud Managed OTLP endpoint](https://www.elastic.co/docs/reference/opentelemetry/managed-inputs/managed-otlp-endpoint)
- [Elastic OpenTelemetry Kubernetes deployment](https://www.elastic.co/docs/solutions/observability/get-started/opentelemetry/use-cases/kubernetes/deployment)
- [Elastic OpenTelemetry Kubernetes application instrumentation](https://www.elastic.co/docs/solutions/observability/get-started/opentelemetry/use-cases/kubernetes/instrumenting-applications)
- [Elastic APM for AWS Lambda](https://www.elastic.co/docs/solutions/observability/apm/ingest/monitor-aws-lambda-functions)
- [Elastic APM service maps](https://www.elastic.co/docs/solutions/observability/apm/service-map)
- [Elastic Universal Profiling requirements](https://www.elastic.co/docs/solutions/observability/infra-and-hosts/get-started-with-universal-profiling)
- [Elastic Workflows](https://www.elastic.co/docs/explore-analyze/workflows)
- [Agent Builder custom tools](https://www.elastic.co/docs/explore-analyze/ai-features/agent-builder/tools/custom-tools)
- [Agent Builder workflow tools](https://www.elastic.co/docs/explore-analyze/ai-features/agent-builder/tools/workflow-tools)
