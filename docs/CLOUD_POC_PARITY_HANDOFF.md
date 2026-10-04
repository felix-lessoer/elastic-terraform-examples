# Azure and GCP PoC parity handoff

**Purpose:** Give a new implementation agent a durable, step-by-step plan for
bringing Azure and Google Cloud PoCs to the quality and customer experience of
the completed AWS PoC.

**Prepared:** 2026-10-04

## Source of truth

The completed AWS reference is:

- branch: `origin/cursor/aws-local-guided-ui-3422`
- reviewed commit: `70d4f0833383e3c05d834ca69d67092a96c927c4`
- pull request: [PR 14](https://github.com/felix-lessoer/elastic-terraform-examples/pull/14)

The earlier modern cloud foundation is:

- branch: `origin/cursor/aws-observability-managed-ec02`
- reviewed commit: `fd5b23dc893ad36b3c0660d2b24f3d1c3d546d67`

This document is stored on the gap-analysis branch, where the modern
`examples/aws`, `examples/azure`, and `examples/gcp` trees are not all present.
A future implementation agent must start from the merged PR 14 result, or from
`origin/cursor/aws-local-guided-ui-3422` if it has not merged. Do not implement
new work in the deprecated root-level `AWS/`, `Azure/`, or `GoogleCloud/`
trees.

Before changing code:

```bash
git fetch origin cursor/aws-local-guided-ui-3422
git log -1 --oneline origin/cursor/aws-local-guided-ui-3422
git ls-tree -r --name-only origin/cursor/aws-local-guided-ui-3422 \
  examples modules tools
```

Follow the current repository branch-naming and pull-request policy when
creating Azure and GCP implementation branches.

## Product outcome

The target is not merely equivalent Terraform resources. An Azure or GCP
customer should receive the same end-to-end PoC experience:

1. start one local PoC Builder UI;
2. enter cloud and Elastic credentials locally;
3. pass actionable preflight checks;
4. select scope and collection depth;
5. review a readable Terraform plan;
6. explicitly approve and apply that saved plan;
7. discover existing customer resources and telemetry without mutation;
8. receive service, dependency, coverage, health, cost, and ownership findings;
9. select named customer workloads for optional visibility canaries;
10. run cloud-specific Insight Engine workflows;
11. land automatically on a useful cockpit;
12. see raw evidence, deterministic insights, and an agent-generated summary;
13. be able to remove or roll back everything introduced by the PoC.

The initial deployment must produce useful outcomes without requiring
application instrumentation.

## Non-negotiable product rules

- Do not deploy a sample workload, traffic generator, or intentionally broken
  service.
- Discover existing customer resources first.
- Reuse existing metrics, logs, traces, collectors, and deployment mechanisms.
- Treat missing telemetry as **unknown**, never as healthy, idle, or unused.
- Separate read-only discovery, telemetry enablement, and workload mutation.
- Require explicit approval for a named resource before workload mutation.
- State AWS/Azure/GCP and Elastic cost implications before enabling telemetry.
- Include exact validation and rollback instructions for every canary.
- Never put a full discovery manifest, secret, or credential in Terraform
  state.
- Do not give an agent generic cloud write credentials.
- Keep write actions in narrow, allow-listed workflows with approval and audit.
- Keep the UI and local server bound to loopback.

## AWS capabilities to reproduce

Use these files from the AWS reference branch as implementation examples.

### Guided UI and lifecycle

- `tools/aws-poc-ui/`
- `tools/aws-poc-ui/server/terraform.ts`
- `tools/aws-poc-ui/server/brownfield.ts`
- `tools/aws-poc-ui/server/credentials.ts`
- `tools/aws-poc-ui/python/aws_brownfield_discovery.py`
- `tools/aws-poc-ui/python/analyze_brownfield.py`
- `tools/aws-poc-ui/python/visibility_adapters.py`

The UI owns preflight, configuration, init, plan, plan review, apply,
discovery, analysis, candidate selection, adapter deployment, workflow
execution, and final links. Direct Terraform remains an advanced automation
path, not the customer Quick Start.

### Terraform and collection

- `examples/aws/main.tf`
- `examples/aws/scripts/discover_*.py`
- `examples/aws/scripts/sync_*.py`
- `examples/aws/scripts/reconcile_fleet_agents.py`
- `modules/aws-cloud/`

Important patterns are deterministic creation order, idempotent sync scripts,
bounded discovery, explicit cleanup, and a clear distinction between managed
collection and agent-required inputs.

### Insight Engine

- `examples/aws/workflows/`
- `examples/aws/agent_workflow_tools.tf`
- `modules/cockpit-dashboard/scripts/seed_aws_insight_indices.py`
- `modules/cockpit-dashboard/scripts/generate_aws_recommendations.py`
- `modules/cockpit-dashboard/scripts/prepare_aws_lookup_indices.py`

The reference implementation creates service-specific insights, unused
resource candidates, coverage, assets, events, and a final agent summary.
Snapshot/reference indices use lookup mode and stable `resource.key` values.

### Cockpit and saved objects

- `modules/cockpit-dashboard/cockpit-aws.ndjson`
- `modules/cockpit-dashboard/aws-security-observability-dashboards.ndjson`
- `modules/cockpit-dashboard/scripts/set_kibana_default_route.py`
- `modules/cockpit-dashboard/scripts/test_aws_cockpit_contract.py`

The cockpit is imported by Terraform, includes its saved-object dependencies,
and becomes the Kibana default route. Supplemental dashboard bundles are
separate Terraform-managed imports.

### Quality contracts

- `examples/aws/workflows/test_workflow_contracts.py`
- `examples/aws/scripts/test_*.py`
- `modules/cockpit-dashboard/scripts/test_aws_*.py`
- `tools/aws-poc-ui/server/app.test.ts`
- `tools/aws-poc-ui/src/api.test.ts`
- `tools/aws-poc-ui/python/test_*.py`

Every cloud implementation needs equivalent cloud-specific contracts.

## Current Azure and GCP starting point

The modern foundation branch already contains:

### Azure

- `examples/azure/`
- `examples/azure/workflows/`
- `modules/azure-cloud/`
- `modules/cockpit-dashboard/cockpit-azure.ndjson`
- `modules/cockpit-dashboard/scripts/seed_azure_insight_indices.py`
- `modules/cockpit-dashboard/scripts/generate_azure_recommendations.py`
- `modules/cockpit-dashboard/scripts/inject_azure_insight_panels.py`

It has Security and optional Observability projects, CSPM, detection rules,
Event Hub collection, VM/storage recommendations, a cockpit, agents, and basic
workflows. It lacks the AWS UI, brownfield discovery, lookup preparation,
Insight Engine summary, workflow tools, broad service insights, and equivalent
tests.

### GCP

- `examples/gcp/`
- `examples/gcp/workflows/`
- `modules/gcp-cloud/`
- `modules/cockpit-dashboard/cockpit.ndjson`
- `modules/cockpit-dashboard/scripts/seed_gcp_insight_indices.py`
- `modules/cockpit-dashboard/scripts/inject_gcp_insight_panels.py`

It has Security and optional Observability projects, CSPM, detection rules,
log sinks and Pub/Sub, compute/storage/load-balancer metrics, agents, a
cockpit, and several workflows. Some GKE, Cloud Run, and Cloud SQL workflows
exist while their metric streams are disabled by default. That mismatch must
be fixed before claiming those insights work.

## Recommended implementation strategy

Do not copy the AWS UI into two independent forks. First extract a shared UI
and cloud-adapter contract, then implement one Azure adapter and one GCP
adapter. Cloud-specific behavior belongs behind typed server-side interfaces;
security controls and lifecycle behavior stay shared.

Suggested target layout:

```text
tools/cloud-poc-ui/
  server/
    cloud-adapter.ts
    lifecycle/
    providers/
      aws/
      azure/
      gcp/
  python/
    common/
    aws/
    azure/
    gcp/
  src/
    shared steps and cloud-specific copy
```

An incremental rename is acceptable. Preserve the working AWS path while
extracting shared code; do not rewrite the entire UI before delivering one
additional cloud.

## Step-by-step common implementation plan

### Phase 0 — Freeze contracts and acceptance tests

1. Branch from the AWS reference implementation.
2. Record current AWS UI, Terraform, workflow, and dashboard tests.
3. Create cloud-neutral schemas for:
   - preflight results;
   - credential status;
   - deployment configuration;
   - discovery progress;
   - resource manifest;
   - dependency evidence;
   - coverage;
   - findings;
   - instrumentation proposals;
   - adapter state and rollback.
4. Add a cloud slug to all generated index, workflow, and saved-object IDs.
5. Define the final customer journey and pass criteria before provisioning.

**Exit gate:** AWS behavior remains unchanged and the shared contracts have
fixture tests.

### Phase 1 — Shared PoC Builder UI

1. Add a cloud selector before credentials.
2. Implement a typed provider adapter with operations for:
   - credential validation;
   - identity/subscription/project lookup;
   - config defaults and validation;
   - Terraform directory and variables;
   - discovery;
   - deterministic analysis;
   - visibility candidate generation;
   - adapter deploy/rollback;
   - workflow IDs and final links.
3. Keep commands and arguments fixed server-side.
4. Keep CSRF, loopback origin restrictions, output allow-lists, secret
   redaction, and `0600` local credential files.
5. Persist operation state and poll it while the page stays open.
6. Show visual progress, elapsed time, current stage, and live command output.
7. Restore completed steps and enabled actions without a browser reload.
8. Render Terraform plans as resource tables, with raw output secondary.

**Exit gate:** a user can leave the page open from preflight through apply;
buttons and steps update without reload, and failures include a customer action.

### Phase 2 — Cloud project topology

For each cloud, decide and document:

- one Observability project, or Security plus Observability with cross-project
  search;
- CSPM/detection-rule scope;
- agentless, managed, agent, or hybrid collection;
- regional/subscription/project scope;
- private-network requirements;
- required licenses and preview limitations.

Do not let dashboards or agent instructions imply Security coverage when only
Observability is deployed.

**Exit gate:** README, variables, outputs, cockpit, and agent text all describe
the same deployed topology.

### Phase 3 — Safe brownfield discovery

1. Implement a read-only cloud session wrapper with:
   - explicit operation allow-list;
   - retries and throttling;
   - per-operation timeout;
   - total API-call budget;
   - resource count limits;
   - bounded regional parallelism;
   - partial-result reporting.
2. Emit progress before every potentially slow service.
3. Prefer cloud inventory/graph APIs before service-by-service listing.
4. Collect resource IDs, regions, state, tags/labels, ownership candidates,
   deployment metadata, configured telemetry, and relationships.
5. Never read secret values; retain references and hashes only.
6. Save the manifest locally first, validate it, then bulk index it after
   Elastic exists.
7. Store only a manifest hash and summary in Terraform outputs.

**Exit gate:** discovery cannot hang indefinitely on one service and produces a
useful partial manifest when permissions are incomplete.

### Phase 4 — Collection and existing-source reuse

1. Inventory existing sinks, diagnostic settings, subscriptions, log buckets,
   workspaces, collectors, and agents.
2. Reuse customer-owned paths before creating duplicate paths.
3. Enable metrics only for service families represented in discovery and
   workflows, unless the customer selects a broader profile.
4. Disable duplicate package inputs explicitly.
5. Reconcile Fleet policies and stale agents after apply.
6. Separate read-only discovery from actions that enable paid cloud services.
7. Expose collection health, permissions, freshness, and expected cloud cost.

**Exit gate:** every enabled integration has a named source, purpose, owner,
freshness result, and cleanup path.

### Phase 5 — Resource-level coverage and findings

Create these cloud-prefixed indices:

```text
{cloud}-cockpit-manifest
{cloud}-cockpit-service-candidates
{cloud}-cockpit-dependencies
{cloud}-cockpit-coverage
{cloud}-cockpit-assets
{cloud}-cockpit-events
{cloud}-cockpit-recommendations
{cloud}-cockpit-findings
{cloud}-cockpit-instrumentation-plans
{cloud}-cockpit-insight-summary
```

Coverage must compare discovered resources with observed metrics, logs,
traces, profiles, owners, and dependencies. A dataset count alone is not
coverage.

Every finding must contain:

- stable resource key;
- category and severity;
- evidence references;
- lookback window;
- confidence;
- contradictory evidence;
- missing telemetry;
- expected value;
- safe next action.

**Exit gate:** findings remain useful without traces and absent data never
creates an unused-resource finding.

### Phase 6 — Dependencies and service candidates

Use evidence in this order:

1. runtime traces;
2. explicit control-plane target relationships;
3. routing/load-balancer relationships;
4. orchestrator relationships;
5. repeated time-resolved network flows;
6. sanitized configured endpoints;
7. correlated request identifiers;
8. metric correlation as a low-confidence hint only.

Keep confirmed, probable, candidate, and hidden relationships distinct.

**Exit gate:** every visible edge exposes source evidence and confidence;
metric correlation alone is never confirmed.

### Phase 7 — Cloud-specific Insight Engine workflows

1. Query live mappings and representative documents before writing ES|QL.
2. Add one workflow per high-value service family.
3. Use current snapshots:
   - delete only the workflow's prior resource/category documents;
   - use deterministic document IDs;
   - cap query and foreach fan-out;
   - include manual and scheduled triggers.
4. Require observed activity for unused-resource logic.
5. Create lookup-mode reference indices before workflows write to them.
6. Use the same stable `resource.key` in assets and recommendations.
7. Add an Insight Engine summary workflow after service workflows complete.
8. Register bounded workflow tools and attach only appropriate tools to agents.

**Exit gate:** final workflow executions are completed, generated documents
exist for available test data, lookup joins work, and a second run is
idempotent.

### Phase 8 — Optional visibility adapters

For each supported resource type:

1. list all eligible candidates, not only the highest-ranked candidate;
2. support select-all and individual selection;
3. clearly state potential cloud cost and workload impact;
4. skip inactive or unsupported resources with a specific reason;
5. preflight required local CLIs or use a native API implementation;
6. snapshot current configuration;
7. create narrowly scoped Elastic credentials;
8. deploy a canary;
9. validate health and signal arrival;
10. persist rollback state with owner-only permissions;
11. clean orphaned credentials safely;
12. provide explicit rollback.

Selection of a candidate is the customer's acknowledgement of the stated cost
and behavior warning. Do not add redundant approval-checkbox friction.

**Exit gate:** every adapter has fixture tests, deploy and rollback contracts,
and a no-op/skip path.

### Phase 9 — Cockpit and default landing

1. Maintain three visible data levels:
   - raw cloud telemetry;
   - deterministic workflow insights;
   - one prominent agent summary.
2. Prefer ES|QL Lens panels for standard visualizations and drill-downs.
3. Use custom content only where its limitations are acceptable.
4. Import exact saved-object exports with deep dependencies.
5. Remove or include dangling tag/data-view references.
6. Deploy supplemental dashboard bundles separately.
7. Set the cockpit as the Kibana default route via the config saved object.
8. Add saved-object contract tests.

**Exit gate:** the configured dashboard opens directly, all imports can be
exported back from Kibana, and there are no missing references.

### Phase 10 — Deployment verification

Required sequence:

1. unit and contract tests;
2. formatting and static validation;
3. commit and push before live testing;
4. review a saved Terraform plan;
5. reject unrelated or destructive actions;
6. apply that exact plan;
7. verify workflow execution statuses, not only HTTP acceptance;
8. verify generated indices and joins;
9. verify dashboards and default route through export APIs;
10. run `terraform plan -detailed-exitcode`;
11. require exit code `0`;
12. delete local plan artifacts;
13. update README, gap register, and PR evidence.

## Azure-specific implementation checklist

### Discovery

- Use Azure Resource Graph as the primary inventory.
- Enumerate approved subscriptions, management groups, locations, resource
  groups, resources, tags, and provider registrations.
- Discover existing diagnostic settings, Event Hubs, Log Analytics workspaces,
  storage destinations, Application Insights, and Azure Monitor alerts.
- Discover Defender for Cloud plans without enabling them.
- Discover AKS, Functions, App Service, VM/VMSS, SQL/PostgreSQL/MySQL, Storage,
  Load Balancer, Application Gateway, Front Door, Service Bus, and Key Vault.
- Infer ownership from tags, resource groups, deployment records, alert action
  groups, and IaC metadata.

### Collection

- Add an attach-to-existing Event Hub/Log Analytics mode.
- Avoid creating duplicate subscription diagnostic settings.
- Expand Azure Monitor metric streams only for selected service families.
- Add Defender alerts, Entra sign-in/audit, NSG flow, Firewall/WAF, AKS audit,
  and resource-specific diagnostics where approved.
- Prefer managed identity or federated credentials over long-lived service
  principal secrets when supported.
- Reconcile both Security and Observability agents if the dual-agent topology
  remains.

### Initial service workflows

Implement and test:

- VM/VMSS utilization and inactive candidates;
- managed disk unattached/idle candidates;
- Functions errors, duration, throttling, and inactivity;
- App Service reliability and latency;
- Azure SQL and flexible database pressure/inactivity;
- AKS cluster/node/workload coverage;
- Load Balancer/Application Gateway health and traffic;
- Storage capacity, requests, errors, and lifecycle opportunities;
- Service Bus backlog and dead-letter growth;
- Azure Service Health events.

### Azure files

Expected additions:

```text
examples/azure/agent_workflow_tools.tf
examples/azure/scripts/
examples/azure/schemas/brownfield-manifest.v1.json
examples/azure/workflows/azure-cockpit-*-insights.yaml
examples/azure/workflows/azure-cockpit-insight-engine-summary.yaml
examples/azure/workflows/azure-ml-datafeed-keeper.yaml
examples/azure/workflows/test_workflow_contracts.py
modules/cockpit-dashboard/scripts/prepare_azure_lookup_indices.py
modules/cockpit-dashboard/scripts/test_azure_cockpit_contract.py
docs/AZURE_POC_GAP_ANALYSIS.md
docs/AZURE_BROWNFIELD_OBSERVABILITY_PLAN.md
```

Expected modifications:

```text
examples/azure/main.tf
examples/azure/variables.tf
examples/azure/outputs.tf
examples/azure/README.md
modules/azure-cloud/
modules/cockpit-dashboard/scripts/seed_azure_insight_indices.py
modules/cockpit-dashboard/scripts/generate_azure_recommendations.py
modules/cockpit-dashboard/scripts/inject_azure_insight_panels.py
modules/cockpit-dashboard/cockpit-azure.ndjson
```

## GCP-specific implementation checklist

### Discovery

- Use Cloud Asset Inventory as the primary inventory.
- Enumerate approved organizations, folders, projects, regions, resources,
  labels, and IAM/service-account references.
- Discover existing Logging sinks, Pub/Sub topics/subscriptions, log buckets,
  metrics scopes, alert policies, Trace, Profiler, Managed Service for
  Prometheus, and existing OTel collectors.
- Discover Security Command Center and Event Threat Detection configuration
  without enabling paid tiers.
- Discover GCE/MIG, GKE, Cloud Run/Functions, Cloud SQL, GCS, Load Balancing,
  API Gateway, Pub/Sub, Spanner/Firestore, Redis, and BigQuery.
- Infer ownership from labels, folders, deployment manager/Terraform metadata,
  alert channels, and service accounts.

### Collection

- Fix the current workflow/metric mismatch first: GKE, Cloud Run, and Cloud SQL
  workflows must not run unless their metric streams are enabled.
- Add an attach-to-existing sink and Pub/Sub mode.
- Avoid duplicate log sinks and subscriptions.
- Add SCC/ETD findings when supported and selected.
- Add Google Cloud Service Health or explicitly report it unavailable.
- Replace exported service-account JSON keys with federation/impersonation
  where Fleet supports it.
- Reconcile both Security and Observability GCE agents if the split remains.

### Initial service workflows

Implement and test:

- GCE/MIG utilization and inactive candidates;
- persistent disk unattached/idle candidates;
- Cloud Run/Functions errors, latency, instances, and inactivity;
- Cloud SQL pressure, connections, storage, and inactivity;
- GKE cluster/node/workload coverage;
- HTTP(S) Load Balancer health, errors, latency, and traffic;
- GCS capacity, request activity, and lifecycle opportunities;
- Pub/Sub backlog and oldest unacked messages;
- BigQuery slot/query pressure and cost signals;
- Google Cloud Service Health events.

### GCP files

Expected additions:

```text
examples/gcp/agent_workflow_tools.tf
examples/gcp/scripts/
examples/gcp/schemas/brownfield-manifest.v1.json
examples/gcp/workflows/gcp-cockpit-*-insights.yaml
examples/gcp/workflows/gcp-cockpit-insight-engine-summary.yaml
examples/gcp/workflows/gcp-ml-datafeed-keeper.yaml
examples/gcp/workflows/test_workflow_contracts.py
modules/cockpit-dashboard/scripts/prepare_gcp_lookup_indices.py
modules/cockpit-dashboard/scripts/generate_gcp_recommendations.py
modules/cockpit-dashboard/scripts/test_gcp_cockpit_contract.py
docs/GCP_POC_GAP_ANALYSIS.md
docs/GCP_BROWNFIELD_OBSERVABILITY_PLAN.md
```

Expected modifications:

```text
examples/gcp/main.tf
examples/gcp/variables.tf
examples/gcp/outputs.tf
examples/gcp/README.md
modules/gcp-cloud/
modules/cockpit-dashboard/scripts/seed_gcp_insight_indices.py
modules/cockpit-dashboard/scripts/inject_gcp_insight_panels.py
modules/cockpit-dashboard/cockpit.ndjson
```

## Quality guideline

### Customer safety

- Default deployment is non-mutating toward customer workloads.
- Discovery and paid-service enablement have separate flags and UI steps.
- All permissions are least privilege and documented by purpose.
- Secrets never reach browser responses, logs, indices, or Terraform outputs.
- Every introduced cloud resource is tagged/labeled and included in cleanup.
- Every canary records original state before mutation.

### Truthfulness

- UI, README, Terraform, cockpit, and agent instructions describe the same
  topology and capabilities.
- A feature is not “covered” because a workflow file exists.
- A service insight is enabled only when required telemetry is enabled and
  verified.
- Missing data is explicit.
- Correlation is not called causation.
- Preview, license, region, and architecture constraints are visible.

### User experience

- Every operation shows pending, running, completed, skipped, or failed.
- Slow discovery emits progress and bounded heartbeats.
- Buttons and step activation update without page reload.
- Errors state what failed, why it matters, and what the operator should do.
- The primary action is obvious; internal setup steps run automatically.
- Candidate selection supports one, many, and all eligible resources.

### Data and insight quality

- Query live field mappings before implementing ES|QL.
- Use bounded lookbacks and document them.
- Require observed metrics for inactivity findings.
- Use stable IDs and snapshot cleanup instead of timestamp-suffixed churn.
- Cap rows and foreach work.
- Store confidence, evidence, missing telemetry, and resource keys.
- Ensure assets and insights can be joined through lookup indices.
- Verify exact queries against a live environment and fixtures.

### Terraform quality

- Plans are saved and the exact reviewed plan is applied.
- Hooks are idempotent and ordered through explicit dependencies.
- Local-exec scripts have retries, timeouts, typed failures, and cleanup.
- Do not hide definitive failures behind `on_failure = continue`.
- Avoid unrelated provider/package upgrades in narrowly scoped changes.
- A completed deployment ends with zero Terraform drift.
- Destroy behavior and orphan cleanup are tested.

### Workflow and agent quality

- Workflows have manual plus scheduled triggers where appropriate.
- Workflows are deterministic before invoking an agent.
- Agent tools have typed parameters, fixed index scopes, and result limits.
- Read-only and write-capable tools are separate.
- Third-party/log content can never count as approval.
- Agent output includes evidence, confidence, contradictions, and blind spots.
- Agent summaries run after service workflows finish.

### Dashboard quality

- Raw data, deterministic insights, and agent summary are visually distinct.
- Panels use ES|QL/Lens where drill-downs are required.
- Saved-object exports include dependencies and have contract tests.
- Default-route changes preserve unrelated advanced settings.
- Supplemental dashboard bundles do not change the cockpit default.
- Dashboard imports are verified by exporting them back from Kibana.

### Test quality

Each cloud must have:

- discovery fixtures for success, denied, throttled, empty, and timeout cases;
- analyzer fixtures for missing telemetry and ambiguous relationships;
- adapter deploy/rollback tests;
- workflow YAML contracts;
- recommendation query tests;
- lookup-index migration tests;
- dashboard saved-object tests;
- UI API security tests;
- UI state-transition tests;
- Terraform format, validate, plan, apply, and final no-drift evidence.

## Definition of done for each cloud

Do not mark Azure or GCP parity complete until all are true:

- [ ] PoC Builder UI is the documented Quick Start.
- [ ] Credentials can be entered locally and are never returned to the browser.
- [ ] Preflight validates cloud identity, Terraform, CLI, Python, and Elastic.
- [ ] Terraform init/plan/apply works without manual commands.
- [ ] Plan resources are reviewable in a table.
- [ ] Browser state advances without reload.
- [ ] Read-only discovery produces a validated manifest and partial results.
- [ ] Existing telemetry paths are reused where possible.
- [ ] Coverage is resource-level, not dataset-presence only.
- [ ] Service candidates and dependencies expose evidence and confidence.
- [ ] Useful findings exist before application instrumentation.
- [ ] All eligible visibility candidates can be selected.
- [ ] Canary adapters include cost, impact, validation, and rollback.
- [ ] Service insight workflows match enabled telemetry.
- [ ] Unused-resource findings require observed inactivity.
- [ ] Reference indices use stable lookup keys.
- [ ] Agent summary is refreshed after deterministic workflows.
- [ ] Cockpit is imported and configured as the default route.
- [ ] Saved objects and supplemental dashboards have no missing references.
- [ ] Cloud-specific tests pass.
- [ ] Live workflows complete successfully.
- [ ] Final Terraform plan has no changes.
- [ ] README and gap documents reflect verified behavior.

## Learnings from the AWS implementation

1. A successful HTTP response from a workflow run means “accepted,” not
   “completed.” Poll the execution and inspect failed steps.
2. Terraform hooks can race when workflows, seeders, and agent summaries start
   together. Enforce creation and execution order.
3. Missing CLIs produce unhelpful `ENOENT` errors unless preflight checks and
   customer-facing remediation exist.
4. A running badge is insufficient. Long discovery needs stage-level progress
   and live output.
5. Cloud APIs can stall on individual services or regions. Every call needs a
   timeout, retry policy, budget, and partial-result behavior.
6. Page reloads must not be required to enable the next step or apply button.
7. Raw Terraform plan text is not a customer review experience; parse resource
   actions into a table.
8. Missing indices and missing fields are normal during greenfield startup.
   Seeders should tolerate unavailable optional telemetry, while still failing
   on authentication and structural errors.
9. Query names from documentation are not enough. Inspect live field mappings
   and execute final ES|QL before deploying workflows.
10. Zero activity and absent telemetry are different. Only the former can
    support an unused-resource finding.
11. Insight fan-out must be bounded; sequential foreach indexing can make a
    workflow run for minutes.
12. Stable document IDs and resource-scoped cleanup prevent duplicate insight
    churn.
13. Lookup mode must be selected when an index is created. Existing standard
    indices require a staged, count-verified migration.
14. Assets and recommendations need the same stable key before lookup joins
    are useful.
15. The recommendation concept and Insight Engine concept should be one
    customer-facing system.
16. The clearest cockpit hierarchy is raw evidence, deterministic insights,
    then an agent summary.
17. An agent summary can be stale if it runs concurrently with service
    workflows. Trigger it after those workflows complete.
18. Saved-object exports can contain dangling tag references even with deep
    export. Validate and include or remove every dependency.
19. Setting Kibana `defaultRoute` requires preserving the complete config saved
    object, not overwriting one field blindly.
20. Supplemental dashboards should be imported separately from the default
    cockpit.
21. Candidate selection should expose all eligible resources and a select-all
    path.
22. Inactive services are not valid canaries. Explain the skip instead of
    failing the whole deployment.
23. Tool dependencies such as `kubectl` must be preflighted or replaced with a
    native API client.
24. Kubernetes authentication and cleanup are separate failure modes; cleanup
    must not obscure the original error.
25. Cleanup of orphaned Elastic credentials must be defensive and must not
    block an unrelated adapter deployment on a recoverable lookup error.
26. Terraform providers can introduce unrelated package-version drift between
    plans. Review exact resource actions before apply.
27. Cloud service enablement can create cost and security side effects. It is
    not discovery and must be a separate customer decision.
28. The UI README and root Quick Start are part of the product. If they show a
    manual Terraform path first, customers will bypass the intended workflow.

## Suggested delivery order

Use separate logical changes and pull requests:

1. shared UI/provider-adapter contracts with AWS regression coverage;
2. GCP telemetry/workflow truth fixes and quality tests;
3. GCP UI, discovery, lookup indices, summary, and cockpit;
4. Azure workflow/lookup/summary quality layer;
5. Azure UI and Resource Graph discovery;
6. GCP approved visibility adapters;
7. Azure approved visibility adapters;
8. shared multicloud consolidation only after both clouds pass their
   definitions of done.

Do not combine Azure and GCP infrastructure changes in one implementation PR.
The shared contracts may be common, but live validation, credentials,
permissions, billing, and rollback are cloud-specific.

## Agent pickup checklist

A new agent should begin with:

1. read this document;
2. read `docs/AWS_POC_COMPETITIVE_GAP_ANALYSIS.md`;
3. read `docs/AWS_BROWNFIELD_OBSERVABILITY_PLAN.md`;
4. inspect the exact AWS baseline branch and commit above;
5. inspect current `examples/azure` and `examples/gcp` on that baseline;
6. choose one cloud and one delivery phase;
7. create a cloud-specific gap document before implementation;
8. turn every acceptance item for that phase into tests or live checks;
9. implement, deploy, and collect no-drift evidence;
10. update this handoff when a learning changes the shared design.

The first implementation priority should be GCP workflow/metric truthfulness,
because workflows currently exist for service metric streams that can be
disabled. The first Azure priority should be lookup indices, Insight Engine
summary, workflow-tool wiring, and cloud-specific contract tests. These changes
raise trust and quality before broader telemetry or workload mutation.
