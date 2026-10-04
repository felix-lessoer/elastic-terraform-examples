# AWS PoC competitive gap analysis

**Scope:** Elastic versus Dynatrace and Datadog for cloud observability, and Splunk for cloud security

**AWS first:** This document intentionally excludes detailed Azure and Google Cloud analysis.

**Research date:** 2026-09-27

**Implementation baseline:** [PR 12](https://github.com/felix-lessoer/elastic-terraform-examples/pull/12), head `b91c89cdf2c968a91987af9b7a45a31e6c0740a1` when last reviewed

**Brownfield correction:** The PoC must not create an example application or other monitored workload. The detailed replacement plan is in [AWS brownfield observability gap plan](AWS_BROWNFIELD_OBSERVABILITY_PLAN.md). Discover the customer's existing services first, derive value from existing telemetry, and instrument only a named customer workload after approval.

## Executive recommendation

Do not try to win by reproducing every competitor screen. Win the PoC with a small number of measurable, cross-domain investigations that competitors cannot complete as simply:

1. correlate AWS infrastructure, application, identity, network, posture, vulnerability, cost, and change data in one evidence trail;
2. let customers inspect and modify the ES|QL used to reach each conclusion;
3. use specialist agents to reason over controlled tools, not unrestricted data;
4. use deterministic Workflows for enrichment and response, with human approval before AWS changes;
5. preserve OpenTelemetry and customer-owned AWS data paths instead of making proprietary instrumentation the only route to value.

PR 12 already provides useful foundations: reproducible Terraform, all-region managed metrics, one EC2 collector for sources that need it, discovery of existing logs, a cockpit, materialized insight indices, recommendations, Workflows, and three specialist agents. It is not yet a complete "Observe + Protect" PoC. The AWS code creates one Serverless Observability project, disables detection-rule bootstrap, does not deploy AWS CSPM/CNVM, and has no application tracing, EKS observability, cases, or approved remediation.

The highest-value next increment is therefore not another dashboard. It is one end-to-end AWS incident story that starts in APM or EKS, correlates a deployment and AWS resource symptom with an identity or posture signal, explains the evidence, opens a case, and offers an approved response.

## How to read this analysis

- **Competitor strength** means the capability is documented and should be assumed credible in a PoC.
- **Testable tradeoff** means the documentation exposes a dependency, limit, packaging seam, or cost dimension. It is not a claim that Elastic is universally better.
- **Close** means use Elastic features to reach expected parity.
- **Differentiate** means demonstrate a workflow that is materially more open, inspectable, cross-domain, or customizable.
- **Do not claim parity** means integrate a specialist product or narrow the claim until Elastic can prove equivalent outcomes.
- Product availability, editions, previews, regions, and commercial terms must be confirmed in the actual trial tenants.

## PR 12 baseline

### What is already compelling

| Existing capability | PoC value |
|---|---|
| Managed AWS collection plus one EC2 Elastic Agent | Demonstrates progressive collection depth without deploying an agent to every host. |
| All-region managed metrics | Gives a broad AWS baseline from one apply. |
| Discovery and attachment of existing CloudWatch and S3 log sources | Reduces disruption and respects customer-owned logging. |
| Regional GuardDuty, Security Hub, Inspector, and Config ingestion | Supplies security findings for correlation without presenting them as native CSPM. |
| AWS cockpit and materialized insight indices | Provides a fast executive entry point and stable inputs for agents. |
| EC2 and S3 recommendation Workflows | Shows repeatable analysis rather than a static dashboard. |
| Observability, security, and recommendations agents | Establishes a role-specific conversational experience. |
| Terraform-owned resources | Makes setup, teardown, and repeated customer demos auditable. |

### Claims that must be corrected or implemented

| Current gap | Evidence in PR 12 | Required action |
|---|---|---|
| AWS is not a combined Security + Observability deployment | `examples/aws/main.tf` creates one Observability project; the AWS README explicitly says no Security project or CSPM policy. | Add Security Complete and cross-project search, or rename the AWS offer to Observability with security-finding correlation. |
| Security KPIs can be empty or misleading | The insight seeder queries Security alerts and CSPM indices that the AWS path does not create. | Point the seeder at a real Security project and report unavailable datasets explicitly. |
| Detection content is absent | `enable_detection_rules = false`. | Enable and validate selected AWS rules with controlled events. |
| Workflow tools are not attached to the agents | Four workflow tools are defined, but their IDs are not passed as additional tools. | Attach only approved, bounded workflows to the relevant agent. |
| Recommendations are narrow | Only EC2 and S3 recommendation workflows exist. | Add EBS, RDS, Lambda, NAT Gateway, and EKS recommendations where evidence is sufficient. |
| Application-level evidence is absent | No APM, OTel, RUM, synthetic, or Lambda trace path is deployed. | Add a representative OTel application path before making full-stack claims. |
| Cloud-native depth is absent | No EKS integration, CSPM, KSPM, or CNVM is deployed on AWS. | Add supported cloud-security and Kubernetes coverage, while documenting preview and regional limits. |
| Response stops at insight | No case lifecycle or approved AWS action exists. | Add alert-to-case and approval-gated containment/remediation workflows. |

## Observability capability snapshot

| Capability | Datadog | Dynatrace | PR 12 today | Elastic PoC target |
|---|---|---|---|---|
| AWS account onboarding | CloudFormation, Terraform, Control Tower, Organizations; 90+ AWS services | Guided CloudFormation and Organizations/StackSets; topology always on | Terraform, managed policies, one agent, existing-source discovery | Keep Terraform path; add organization preset, health checks, and time-to-first-data report |
| Infrastructure | CloudWatch plus Agent, resource catalog, processes and containers | CloudWatch plus OneAgent/Smartscape | Broad managed metrics and cockpit | Add topology/entity view and collection-health evidence |
| APM | Deep traces, profiling, deployment comparison | OneAgent auto-instrumentation and causal context | Missing | Discover existing APM/OTel first; generate approval-ready instrumentation plans for high-value customer services |
| Logs | Pipelines, archive/rehydration, Flex Logs | Grail logs with entity correlation | Existing-source discovery and AWS datasets | Show ECS normalization, tiered retention, and source-to-search latency |
| RUM/synthetics | RUM, replay, tests, replay-to-test | RUM, replay, public/private synthetic locations | Missing | Add one browser journey and synthetic; do not over-invest before core AWS story works |
| Lambda/serverless | Extension/library, cold starts, inferred resources, Step Functions | Lambda layer/extension, cold starts, async propagation | Metrics and discovered logs only | Add OTel/X-Ray-compatible trace path and cold-start/error workflow |
| EKS | Operator, Cluster Agent, admission injection | Operator, OneAgent/CSI/webhook, ActiveGate | Missing | OTel Operator plus Kubernetes integration, KSPM, and selective instrumentation |
| Network | Cloud Network Monitoring, DNS, path analysis | OneAgent connections, NetFlow, VPC log analysis | VPC flow logs and firewall metrics | Correlate flow denies with services, identities, and security findings |
| Database | DBM query samples, plans, waits, service correlation | RDS metrics plus remote SQL extensions | RDS metrics only | Add logs/Performance Insights where supported and an RDS contention scenario |
| Cost | CUR-backed cloud cost and recommendations | FOCUS-based AWS billing and cost/carbon | Billing metrics plus EC2/S3 recommendations | Add CUR/FOCUS ingestion and cost-per-service or cost-per-transaction |
| AI/RCA | Bits investigations | Davis causal analysis and Assist | Specialist agents over insight indices | Produce an inspectable evidence pack with confidence and missing-telemetry fields |
| Automation | Workflows, cases, incidents, on-call | Workflows and approval-gated actions | Four recommendation/refresh workflows | Add alert-to-case, deterministic branches, approval, action audit, and rollback |
| OpenTelemetry | Supported, with documented differences by intake path | Native OTLP HTTP/protobuf with documented restrictions | Not demonstrated | Make portable OTel attributes and replaceable collectors a scored PoC criterion |

## Observability gap register

Every gap below includes an Elastic response. Priorities assume the goal is to win a combined AWS Observability and Security PoC.

### O1 — Guided onboarding and visible collection health

**Competitor strength:** Datadog and Dynatrace provide guided CloudFormation onboarding, connection status, recommended service sets, and organization-scale options.

**PR 12 gap:** Setup is reproducible but Terraform-heavy. Success is reported mostly through outputs and manual checks. Local-exec synchronization adds dependencies that can fail after infrastructure has been created.

**Elastic response — close and differentiate (P0):**

- add `demo`, `standard`, and `full` collection profiles;
- add an AWS Organizations/OU path with least-privilege cross-account roles;
- create a setup report containing elapsed time, resources discovered, active datasets, first-event timestamps, missing permissions, throttling, and estimated AWS transport cost;
- index setup checks into `aws-cockpit-coverage` and let the Observability Triage agent explain only documented failures;
- make sync scripts idempotent and add fixture-based tests.

**Winning proof:** From an empty project, the customer can identify what is working, what is missing, why it is missing, and how much AWS-side plumbing was created without reading Terraform logs.

### O2 — Automatic topology and entity context

**Competitor strength:** Dynatrace Smartscape/Davis and Datadog Resource Catalog/service views make topology a first-class investigation input.

**PR 12 gap:** The cockpit summarizes assets and coverage but is not a live service/resource dependency graph.

**Elastic response — close (P1):**

- detect existing customer APM, OTel, and X-Ray telemetry and reuse it before proposing new instrumentation;
- normalize AWS ARN, account, region, availability zone, Kubernetes, service, deployment, and owner fields;
- create ES|QL tools for upstream/downstream dependencies, recent changes, impacted resources, and telemetry gaps;
- link cockpit assets to APM services, traces, infrastructure, and security entity pages.

**Winning proof:** Starting from one alert, reach the affected service, deployment, pod or Lambda, RDS dependency, AWS resource, and owner without manually copying identifiers.

### O3 — Deep APM and low-friction instrumentation

**Competitor strength:** Datadog APM is mature, while Dynatrace OneAgent automatic injection is especially persuasive in short PoCs.

**PR 12 gap:** No APM or profiling data is collected.

**Elastic response — close with a brownfield openness differentiator (P0/P1):**

- inventory existing EC2/ASG, ECS, EKS, Lambda, API Gateway, ELB, and RDS workloads;
- detect existing Elastic APM, OTel collectors/exporters, X-Ray, AMP/Prometheus, logs, and deployment metadata;
- automatically rank real customer services by criticality, active symptoms, dependency centrality, telemetry gap, instrumentation feasibility, risk, and estimated cost;
- generate an exact instrumentation proposal for a named customer workload, including owner, deployment diff, permissions, restart/replacement, canary, success criteria, and rollback;
- preserve standard resource attributes and document every Elastic-specific enrichment;
- modify the workload only after explicit approval, preferably through the customer's deployment mechanism;
- score trace completeness, collector overhead, and the ability to redirect telemetry to another backend.

**Winning proof:** Diagnose an existing customer incident or anomaly using current telemetry, then show how one approved canary closes a demonstrated evidence gap. Do not deploy or break a sample service.

### O4 — Lambda and event-driven application depth

**Competitor strength:** Datadog and Dynatrace expose cold starts, invocation traces, async relationships, and Lambda-specific diagnostics.

**PR 12 gap:** Lambda metrics and discoverable CloudWatch logs are present; distributed traces and async causality are not.

**Elastic response — close (P1):**

- discover existing API Gateway, Lambda, SQS, SNS, and EventBridge relationships and tracing/logging state;
- select an active customer flow only when current evidence shows a high-value tracing gap;
- generate a version/alias-aware layer or OTel instrumentation plan and require approval before changing the function;
- add tools for cold-start impact, timeout/error concentration, memory pressure, and broken trace links;
- correlate function deployment/configuration changes from CloudTrail;
- add a Workflow that opens a case when latency and cold-start regressions cross defined thresholds.

**Winning proof:** Explain a user-visible failure across synchronous and asynchronous hops, including the exact function version and recent AWS change.

### O5 — EKS onboarding and application-to-cluster correlation

**Competitor strength:** Both observability competitors have mature Operators, automatic discovery, and optional injection.

**PR 12 gap:** The modern AWS example has no EKS path.

**Elastic response — close and differentiate on explicit controls (P1):**

- discover existing EKS clusters, node groups, Fargate profiles, add-ons, and telemetry; use the Kubernetes API only after approval;
- deploy infrastructure collection only with cluster approval and scoped RBAC;
- propose application injection only for a selected existing workload or namespace and document webhook, restart, privilege, and rollback requirements;
- add KSPM and Elastic Defend only where supported and consented;
- correlate traces with pods, nodes, deployments, audit events, posture findings, and runtime alerts;
- expose collector and agent health in the cockpit.

**Winning proof:** A bad deployment is traced from user impact to pod/node pressure, while the customer can see exactly which components and privileges were added.

### O6 — Database query-level diagnosis

**Competitor strength:** Datadog DBM and Dynatrace database extensions provide waits, normalized queries, plans, and application context.

**PR 12 gap:** RDS monitoring stops at CloudWatch metrics.

**Elastic response — close selectively (P1):**

- enable supported RDS logs, Enhanced Monitoring, and Performance Insights ingestion;
- reuse existing caller traces; otherwise identify and propose instrumentation for the highest-value real caller;
- create tools for query fingerprint regression, waits/connections, storage pressure, and calling services;
- record database permissions and network paths required for each level of depth.

**Winning proof:** Attribute a latency regression to a query fingerprint and calling service, not merely high RDS CPU.

### O7 — Network troubleshooting

**Competitor strength:** Datadog provides purpose-built cloud network and path experiences; Dynatrace combines connection data, NetFlow, and AWS logs.

**PR 12 gap:** VPC Flow Logs and firewall metrics are useful raw material, but there is no service-aware path investigation.

**Elastic response — differentiate through security correlation (P1):**

- add ES|QL tools for rejected flows, new destinations, cross-account paths, and top talkers;
- enrich flows with workload, service, identity, threat intelligence, and Security Group/NACL change data;
- visualize the impacted path and include raw-event links;
- trigger a case when a service regression and a network-policy change overlap.

**Winning proof:** One investigation explains both the application symptom and the policy or suspicious network activity behind it.

### O8 — RUM, session replay, and synthetics

**Competitor strength:** Datadog's RUM-to-synthetic flow and both competitors' replay experiences are strong visual PoC moments.

**PR 12 gap:** No digital-experience data is present.

**Elastic response — close narrowly (P2):**

- discover customer endpoints and existing synthetics, then propose one high-value journey only with service-owner approval;
- correlate frontend errors and synthetic failures with backend traces and AWS dependencies;
- configure privacy masking and document captured fields;
- do not claim replay-to-test parity unless demonstrated in the selected Elastic release.

**Winning proof:** Start with a failed journey and reach the backend/AWS cause. Treat replay authoring convenience as a competitor advantage if Elastic cannot prove it.

### O9 — Causal RCA and AI investigation

**Competitor strength:** Dynatrace Davis emphasizes topology-aware causal analysis; Datadog Bits tests hypotheses against telemetry.

**PR 12 gap:** Agents search materialized summaries but do not yet produce a consistent, auditable incident evidence pack.

**Elastic response — differentiate rather than claim algorithmic parity (P0):**

- give the Observability Triage agent narrowly parameterized tools for symptoms, dependencies, changes, logs, traces, infrastructure, security, and historical incidents;
- require structured output: impact, observations, likely cause, confidence, contradictory evidence, missing telemetry, and next checks;
- persist executed query IDs/results and the final narrative in the case;
- combine ML anomaly scores with deterministic ES|QL; never present correlation as proven causation;
- benchmark with partially instrumented incidents, where topology-dependent systems may also have blind spots.

**Winning proof:** An evaluator can reproduce every material conclusion and see what the agent did not know.

### O10 — Incident, case, and on-call lifecycle

**Competitor strength:** Datadog combines cases, incident management, on-call, workflows, and notifications. Dynatrace can trigger workflow actions from problems.

**PR 12 gap:** It stops at dashboards, recommendations, and conversational tools.

**Elastic response — close the response path (P0):**

- alert or anomaly → evidence queries → agent summary → deduplicated Elastic Case;
- attach source events, trace links, entities, runbook, owner, and SLA;
- notify Slack/Teams and connect Jira, ServiceNow, or PagerDuty when those are the customer's systems of record;
- add approval-gated AWS actions through a narrowly scoped Lambda or Step Functions endpoint;
- record approver, parameters, result, and rollback guidance.

**Winning proof:** Complete detection-to-decision in one scripted scenario. Do not claim to replace a customer's on-call platform if connectors provide a better outcome.

### O11 — FinOps correlated with reliability

**Competitor strength:** Datadog ingests AWS cost data and provides recommendations; Dynatrace has AWS FOCUS billing and cost/carbon views.

**PR 12 gap:** Billing telemetry and EC2/S3 recommendations exist, but invoice-grade allocation and service-unit economics do not.

**Elastic response — differentiate (P1):**

- ingest CUR 2.0 or FOCUS-shaped billing data;
- normalize account, owner, application, environment, and cost-center tags;
- calculate resource and service cost immediately; calculate unit cost only for real services with request/transaction telemetry;
- add EBS, NAT Gateway, RDS, Lambda, idle load balancer, and storage-lifecycle recommendations;
- require performance/SLO evidence before recommending rightsizing;
- create an approval workflow that opens a ticket rather than changing production directly.

**Winning proof:** Explain whether a cost change came from traffic, a deployment, waste, or pricing, and show the reliability impact of the recommendation.

### O12 — Data portability, retention, and cost predictability

**Competitor tradeoffs to test:** Datadog has many separate billing dimensions and intake-path differences for OTel. Dynatrace DPS meters ingest/process, retention, query scans, workflows, and egress; direct OTLP has protocol/model limits.

**PR 12 gap:** It warns about costs but does not produce a comparative model.

**Elastic response — differentiate through transparent measurement (P0):**

- publish bytes/events by source, mapped/unmapped fields, cardinality, retention tier, query volume, and AWS transport costs;
- use identical telemetry and retention scenarios for all vendors;
- include baseline, burst, high-cardinality, and long-retention cases;
- test OTLP HTTP/gRPC, supported metric types, payload limits, sampling, enrichment, and backend replacement;
- separate public list prices from negotiated quotes and avoid unsupported "cheaper" claims.

**Winning proof:** Give the customer a reproducible cost and portability worksheet populated from the PoC, not a headline-price comparison.

## Security capability snapshot

| Capability | Splunk | PR 12 today | Elastic PoC target |
|---|---|---|---|
| AWS onboarding | Data Manager/CloudFormation/StackSets; push and pull paths | GuardDuty, Security Hub, Inspector, Config plus CloudTrail/VPC inputs | Organization preset, latency/quality report, ECS validation |
| SIEM content | ES detections, Security Content/ESCU, MITRE mappings | Detection bootstrap disabled | Curated AWS rule pack validated by controlled events |
| Risk | Risk-based alerting over assets and identities | No demonstrated entity risk | Entity risk plus asset criticality and inspectable contributions |
| UEBA | UEBA baselines contribute to entity risk | Event-rate ML only | AWS identity and host ML with explainable risk linkage |
| Threat intelligence | Native feeds plus TIM Cloud | Not demonstrated | STIX/TAXII feeds, indicator matching, expiry/confidence |
| Investigation | Mission Control queue, findings, groups, timelines | Security agent over summary indices | Attack Discovery, Timeline, entities, cases, Agent Builder |
| SOAR | Mature SOAR playbooks, apps, prompts, workbooks | Workflows do not perform response | Bounded Workflows, approvals, connectors, case audit |
| Phishing/malware | Attack Analyzer and automated threat analysis | Missing | Integrate sandbox/reputation tools; do not claim parity without detonation |
| Cloud security | Native AWS findings and exposure context; not automatically full CNAPP | Third-party findings, no native CSPM/CNVM | CSPM, KSPM, asset inventory, CNVM, Defend where supported |
| Security Lake | Federated OCSF architecture with recent local tier | Not demonstrated | S3/SQS OCSF ingest plus explicit hot/retained-data design |
| Security AI | Investigation, detection, triage, malware, phishing agents by edition/region | One custom security analyst | Controlled AWS triage and response agents with evidence |

## Security gap register

### S1 — AWS data onboarding, normalization, and freshness

**Splunk strength:** Mature AWS push/pull patterns, organization onboarding, and operational familiarity.

**PR 12 gap:** Collection breadth is promising, but there is no committed source-to-search quality harness. Some managed log streams are disabled in favor of discovered customer sources.

**Elastic response — close and differentiate (P0):**

- validate CloudTrail, GuardDuty, Security Hub, Inspector, Config, VPC Flow, Route 53 Resolver, WAF, Network Firewall, EKS audit, and Security Lake paths that are in scope;
- report source timestamp, AWS publication delay, queue delay, ingest delay, parse failures, ECS conformance, duplicates, and daily volume;
- distinguish vendor latency from source publication latency, especially GuardDuty frequency;
- expose missing permissions and stale datasets in the cockpit and triage agent.

**Winning proof:** Every selected source has a visible freshness and data-quality SLO.

### S2 — Detection content and engineering

**Splunk strength:** Security Content exposes SPL, prerequisites, risk messages, MITRE mappings, and tuning hooks.

**PR 12 gap:** AWS detection-rule bootstrap is disabled.

**Elastic response — close (P0):**

- enable only the AWS prebuilt rules supported by collected datasets;
- add ES|QL rules for service impairment, unusual-region activity, risky role assumption, access-key creation followed by discovery, and suspicious network behavior;
- map each rule to required datasets, ATT&CK, expected volume, suppression, and response;
- include controlled test events and expected alerts in an automated validation script.

**Winning proof:** A rule is not counted as coverage until its source event, alert, entity, and case path are demonstrated.

### S3 — Risk-based prioritization

**Splunk strength:** RBA accumulates weaker signals against assets and identities and promotes meaningful combinations.

**PR 12 gap:** The security KPI is a count of findings, not a demonstrated entity-risk model.

**Elastic response — close and make it inspectable (P0):**

- enable entity risk scoring for users, hosts, and services;
- import asset criticality for production accounts, privileged roles, internet-facing assets, and sensitive data stores;
- build an ES|QL "risk contributions" tool showing source rule, score, time decay, entity, and criticality;
- let the Security Analyst explain why an entity is high risk with links to every contributing event.

**Winning proof:** The same low-severity events produce different priorities for a sandbox role and a production administrator, with reproducible math.

### S4 — UEBA and anomaly detection

**Splunk strength:** UEBA baselines users/devices and feeds entity risk, although underlying logic is not fully user-editable and some services have edition/region limits.

**PR 12 gap:** ML jobs monitor event and finding rates, not user/entity behavior.

**Elastic response — close selectively (P1):**

- enable supported AWS identity ML jobs such as unusual commands by user and error spikes;
- add peer/context fields including account, role type, source network, region, and asset criticality;
- combine anomaly scores with deterministic sequences rather than alerting on every anomaly;
- show model rationale and influential fields; document where models are not editable.

**Winning proof:** Detect a novel IAM/STS behavior that a static rule misses, then show why it was unusual and how it changed entity risk.

### S5 — Threat intelligence

**Splunk strength:** Multiple feed formats, weighted sources, matching, and investigation enrichment.

**PR 12 gap:** Threat-intelligence ingestion and matching are not part of the AWS story.

**Elastic response — close (P1):**

- ingest STIX/TAXII and selected commercial/open feeds;
- enforce confidence, age, and expiration;
- match against VPC, DNS, WAF, CloudTrail, and workload events;
- display feed, confidence, matched field/value, related entities, and risk contribution;
- use Workflows for additional enrichment only after deduplication.

**Winning proof:** An indicator match adds context without creating an unactionable duplicate-alert storm.

### S6 — Analyst investigation and case management

**Splunk strength:** Mission Control provides a mature queue, finding groups, investigations, timelines, ownership, disposition, notes, risk, and automation history.

**PR 12 gap:** There is no security analyst queue or case lifecycle.

**Elastic response — close (P0):**

- use Attack Discovery for grouped narratives where licensed and available;
- use Timeline for raw events/sequences, entity pages for activity/risk, and Cases for ownership and evidence;
- give Agent Builder tools for identity activity, related alerts, cloud resources, network flows, vulnerabilities, posture, and similar cases;
- persist evidence and disposition, not only generated prose;
- compare analyst clicks, context switches, time to disposition, and evidence reproducibility.

**Winning proof:** Triage the same AWS attack in both products and produce a defensible case without hidden agent steps.

### S7 — SOAR and approved AWS response

**Splunk strength:** Splunk SOAR has a mature app/playbook ecosystem, workbooks, prompts, response plans, and automation history.

**PR 12 gap:** Existing Workflows refresh assets/recommendations; they do not execute security response.

**Elastic response — close common AWS actions, integrate for long-tail actions (P0/P1):**

- create identity triage and GuardDuty/Security Hub response workflows;
- enrich deterministically, invoke the agent only for bounded classification/summarization, and deduplicate by entity/resource ARN;
- require approval before disabling credentials, quarantining EC2, changing a security group, or invoking remediation;
- execute through least-privilege Lambda/Step Functions and record all inputs/outputs;
- use connectors to an existing SOAR when its app ecosystem is the better answer.

**Winning proof:** Safely contain one controlled incident end to end. Do not claim broad SOAR parity from a handful of workflows.

### S8 — Phishing and malware analysis

**Splunk strength:** Attack Analyzer follows links, extracts nested content, detonates supported files, and preserves attack-chain forensics.

**PR 12 gap:** No equivalent capability is deployed.

**Elastic response — do not claim parity (P2):**

- integrate an existing sandbox, reputation, email-security, or malware-analysis service;
- use Workflows to parse artifacts, enrich, match indicators, and open/update a case;
- use an agent for structured summary and recommended action, not as a substitute for detonation;
- score the integrated outcome only if the complete chain and forensic evidence are available.

**Winning proof:** Honest integration and unified evidence are better than an unsupported native-equivalence claim.

### S9 — Native cloud security posture, vulnerability, and runtime context

**Splunk tradeoff:** Splunk ingests strong AWS-native security findings and offers exposure analytics, but public ES material does not by itself establish complete native CNAPP parity.

**PR 12 gap:** It ingests GuardDuty/Security Hub/Inspector/Config but does not deploy Elastic CSPM, KSPM, CNVM, cloud asset discovery, or runtime defense.

**Elastic response — key differentiation (P0/P1):**

- deploy AWS CSPM, KSPM for EKS, CNVM, cloud asset inventory, and Elastic Defend only where the current product supports the customer's regions and architecture;
- correlate failed controls, vulnerabilities, runtime behavior, CloudTrail, network activity, and application ownership;
- label preview features and disclose constraints, including current CNVM coverage, scan cadence, architecture, and region/partition support;
- create a prioritization tool based on exploitability evidence, exposure, runtime presence, asset criticality, and active threat behavior.

**Winning proof:** Turn a posture or vulnerability finding into a prioritized, application-aware incident rather than another isolated list.

### S10 — Amazon Security Lake and customer-owned history

**Splunk strength:** Federated Analytics supports OCSF Security Lake data with a recent local detection tier and remote historical hunting.

**PR 12 gap:** No Security Lake/OCSF path is demonstrated.

**Elastic response — close with a transparent storage design (P1):**

- ingest selected OCSF Security Lake data through S3/SQS;
- retain a hot detection window in Elastic and define the customer-owned historical path explicitly;
- validate mappings and detection compatibility rather than assuming raw OCSF activates ECS content;
- measure remote/reingest search latency and cost for historical investigations.

**Winning proof:** The customer understands which data is searchable for detections, which is retained in AWS, and the cost/time to investigate older events.

### S11 — Security AI and agent governance

**Splunk strength:** Current ES releases document investigation, detection-building, triage, guided-response, malware, and phishing agents, with edition, region, model, and SOAR prerequisites.

**PR 12 gap:** One Security Analyst agent exists, but its inputs are incomplete and its workflow tools are not attached.

**Elastic response — differentiate on bounded, customer-editable tools (P0):**

- split tools by read-only investigation and write-capable response;
- use typed parameters, explicit index scopes, result limits, and least privilege;
- require agents to return evidence, confidence, contradictory signals, and missing data;
- expose tool definitions and ES|QL for customer modification;
- allow response only through named Workflows with approvals and audit;
- test prompt injection from log/event content and prohibit third-party content from granting approval.

**Winning proof:** The customer can inspect and govern exactly what the agent can read, conclude, and change.

## Differentiated AWS PoC scenarios

### Scenario A — Existing customer service degradation

1. Discover customer services and rank active health anomalies from existing alarms, metrics, logs, traces, and AWS Health.
2. Select a real degradation or recent incident with the service owner; do not create or inject a failure.
3. Correlate deployment/configuration changes, traces when present, compute pressure, dependencies, VPC flows, and CloudTrail.
4. Have the Observability Triage agent produce an evidence pack, confidence, contradictory evidence, and missing telemetry.
5. Open a case and route it to the inferred or confirmed owner.
6. If missing telemetry blocks the investigation, generate an approval-ready canary instrumentation plan for that existing workload.

**Value:** Demonstrates an investigation that crosses the normal observability/security boundary.

### Scenario B — Compromised AWS identity affecting a production workload

1. Use an existing customer finding or a customer-approved validation event; do not create a new workload.
2. Combine prebuilt rules, ES|QL sequences, ML anomaly, asset criticality, and entity risk.
3. Correlate GuardDuty/Security Hub, CloudTrail, network flow, affected workload, and application ownership.
4. Use the Security Analyst to summarize evidence and missing context.
5. Require approval before disabling credentials or quarantining an instance.

**Value:** Competes directly with Splunk RBA, UEBA, Mission Control, and SOAR while showing application impact.

### Scenario C — Existing Lambda reliability, cost, and change

1. Discover active API Gateway, Lambda, queue, and event-bus relationships.
2. Rank real functions by errors, throttles, duration, concurrency, log evidence, cost, and missing traces.
3. Correlate an existing anomaly with function version, CloudTrail configuration change, logs, available traces, and invocation cost.
4. If tracing is absent, generate a layer/extension canary plan against a named function alias or version.
5. Create a recommendation with expected value, change impact, rollback, and an approval-gated ticket.

**Value:** Competes with purpose-built Datadog/Dynatrace serverless views and adds transparent unit economics.

### Scenario D — Posture finding to runtime priority

1. Use an existing CSPM or vulnerability finding in the approved customer scope.
2. Add internet exposure, application ownership, runtime presence, and available threat activity.
3. Prioritize the finding using evidence rather than base severity alone.
4. Open a case and propose the least disruptive remediation.

**Value:** Differentiates from a SIEM that only ingests AWS-native findings.

## Prioritized implementation plan

### P0 — Make the promise true

1. Decide and document whether AWS is Observability-only or combined Observe + Protect.
2. For combined scope, add a Security project/cross-project experience and real CSPM/detection inputs.
3. Correct seeder, cockpit, and agent behavior when security datasets are absent.
4. Enable a curated AWS detection pack and automated test events.
5. Add brownfield resource/service discovery, detect existing APM/OTel/X-Ray, and index deployment metadata.
6. Add entity risk, asset criticality, Cases, and one approved-response Workflow.
7. Attach bounded workflow tools to the correct agents.
8. Add setup, freshness, ECS quality, and cost measurements.
9. Publish a scripted 20-minute demo and fallback data set.

### P1 — Build the winning cross-domain story

1. Add EKS discovery and approved infrastructure collection; propose selective OTel instrumentation only for existing workloads with demonstrated value.
2. Discover Lambda relationships and tracing state; add tracing only through an approved function canary.
3. Add RDS query-level evidence and Performance Insights where supported.
4. Add CSPM/CNVM/cloud asset/runtime correlations within documented support.
5. Add CUR/FOCUS and cost-per-service/transaction.
6. Add threat intelligence, AWS identity ML, Security Lake, and network tools.
7. Expand recommendations to EBS, RDS, Lambda, NAT Gateway, and EKS.

### P2 — Broaden after the core story is reliable

1. Add RUM, replay where available, and synthetics.
2. Integrate phishing/malware sandboxes without claiming native detonation parity.
3. Add multi-region VPC Flow provisioning options.
4. Add dashboard/query regression tests and screenshot evidence.
5. Add scale presets and retention/cost experiments.

## PoC scorecard

Use the same AWS accounts, regions, services, traffic, incidents, retention, and operator skill level for every vendor.

| Category | Measures |
|---|---|
| Time to value | Stack start to first metric, log, trace, finding, useful dashboard, detection, and case |
| Coverage | Target resources discovered; services with metrics/logs/traces/security; regions/accounts covered |
| Data quality | ECS/semantic-convention conformance, parse failures, duplicates, missing dimensions, timestamp lag |
| Investigation | Time/clicks/context switches to defensible cause; evidence reproducibility; missing-context disclosure |
| Alert quality | Alerts per scenario, grouped incidents, false positives, risk prioritization, suppression behavior |
| Automation | Enrichment success, approval enforcement, action audit, rollback, connector reliability |
| AI | Correctness, evidence links, repeatability, contradictory evidence, permissions, prompt-injection resistance |
| Operations | Components, IAM/RBAC, CPU/memory, upgrades, private-network support, failure recovery |
| Portability | OTel completeness, vendor-specific fields, collector replacement, data export/egress |
| Cost | Vendor dimensions plus CloudWatch, Firehose, S3, Lambda, egress; baseline/burst/cardinality/retention |

Pre-register the scenarios and pass criteria. Vendor-authored documentation proves availability, not comparative accuracy, overhead, or price.

## Positioning: what to say and what not to say

### Defensible messages

- "Elastic combines open search, observability, security, and customer-defined automation over the same AWS evidence."
- "The customer can inspect and change the ES|QL and tools behind the agent's conclusions."
- "Reasoning is bounded to read-only tools; changes occur through audited, approval-gated Workflows."
- "We will measure portability, source-to-search latency, operational footprint, and full cost using your workload."
- "We can correlate native AWS findings with posture, vulnerability, runtime, identity, application, and cost context where the enabled Elastic features support it."

### Avoid until demonstrated

- "Elastic has automatic causal RCA equivalent to Davis."
- "Elastic is cheaper than Datadog, Dynatrace, or Splunk."
- "Elastic Workflows replace the full Splunk SOAR ecosystem."
- "Elastic natively replaces Attack Analyzer."
- "Raw OTel or OCSF data automatically activates every Elastic dashboard and rule."
- "PR 12 already deploys AWS CSPM, detection rules, APM, EKS, or complete security."
- "Agent-generated correlation proves causation."

## Source notes

All URLs were accessed on 2026-09-27. Documentation is continuously updated. Some pages describe preview, region-limited, edition-specific, or separately licensed functionality. Verify the actual PoC tenant and written quote.

### Datadog

- [Getting Started with AWS](https://docs.datadoghq.com/getting_started/integrations/aws/) — onboarding, collection timing, separate log setup, and no historical metric backfill.
- [Amazon Web Services integration](https://docs.datadoghq.com/integrations/amazon-web-services/) — supported AWS services, setup paths, permissions, and resource collection.
- [Resource Catalog](https://docs.datadoghq.com/infrastructure/resource_catalog/) — resource metadata, relationships, telemetry, changes, security, and cost.
- [Application Performance Monitoring](https://docs.datadoghq.com/tracing/) — traces and cross-signal correlation.
- [AWS Lambda monitoring](https://docs.datadoghq.com/serverless/aws_lambda/) and [Step Functions monitoring](https://docs.datadoghq.com/serverless/step_functions/installation/) — serverless depth and prerequisites.
- [Network Monitoring](https://docs.datadoghq.com/network_monitoring/) and [Database Monitoring](https://docs.datadoghq.com/database_monitoring/) — purpose-built network and database experiences.
- [Kubernetes single-step APM instrumentation](https://docs.datadoghq.com/tracing/trace_collection/single-step-apm/kubernetes/) — EKS/Kubernetes injection.
- [Cloud Cost recommendations](https://docs.datadoghq.com/cloud_cost_management/recommendations/) — cost optimization.
- [Datadog Security](https://docs.datadoghq.com/security/) — security overlap.
- [Bits Investigation](https://docs.datadoghq.com/bits_ai/bits_investigation/) — AI investigation.
- [Case automation](https://docs.datadoghq.com/incident_response/case_management/automation_rules/) — response workflow.
- [OTLP intake](https://docs.datadoghq.com/opentelemetry/setup/otlp_ingest/) — supported paths and caveats.
- [Billing definitions](https://docs.datadoghq.com/account_management/billing/pricing/) and [public list pricing](https://www.datadoghq.com/pricing/list/) — commercial dimensions.

### Dynatrace

- [AWS Cloud Platform Monitoring onboarding](https://docs.dynatrace.com/docs/ingest-from/amazon-web-services/aws-onboarding) — current guided AWS integration.
- [AWS Organizations](https://docs.dynatrace.com/docs/ingest-from/amazon-web-services/aws-organizations) and [AWS connection settings](https://docs.dynatrace.com/docs/ingest-from/amazon-web-services/create-an-aws-connection/aws-connection-app-settings) — organization setup, resources, and limits.
- [CloudWatch metrics and supported AWS services](https://docs.dynatrace.com/docs/ingest-from/amazon-web-services/ingest-telemetry/aws-cloudwatch-metrics) — coverage.
- [Grail concepts](https://docs.dynatrace.com/docs/platform/grail/dynatrace-grail/concepts) and [Organize Grail data](https://docs.dynatrace.com/docs/platform/grail/organize-data) — data and retention model.
- [OneAgent monitoring modes](https://docs.dynatrace.com/docs/platform/oneagent/monitoring-modes/monitoring-modes) and [ActiveGate capabilities](https://docs.dynatrace.com/docs/ingest-from/dynatrace-activegate/capabilities) — deployment depth and components.
- [Lambda tracing](https://docs.dynatrace.com/docs/ingest-from/amazon-web-services/integrate-into-aws/aws-lambda-integration/trace-lambda-functions) — serverless monitoring.
- [Kubernetes full-stack onboarding](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/deployment/full-stack-observability) — Operator, CSI, webhook, and ActiveGate.
- [Databases](https://docs.dynatrace.com/docs/observe/infrastructure-observability/databases) — remote database requirements.
- [Cost & Carbon Optimization](https://docs.dynatrace.com/docs/observe/business-observability/cost-and-carbon-optimization) — FOCUS/AWS cost.
- [Root-cause analysis](https://docs.dynatrace.com/docs/dynatrace-intelligence/root-cause-analysis) — Davis and topology-aware analysis.
- [Workflow concepts](https://docs.dynatrace.com/docs/analyze-explore-automate/workflows/concepts) — automation.
- [Dynatrace OTLP API](https://docs.dynatrace.com/docs/ingest-from/opentelemetry/otlp-api) and [OTLP metric ingestion](https://docs.dynatrace.com/docs/ingest-from/opentelemetry/otlp-api/ingest-otlp-metrics/about-metrics-ingest) — protocol and data-model constraints.

### Splunk

- [Splunk security pricing/features](https://www.splunk.com/en_us/products/pricing/cyber-security.html) — Essentials/Premier packaging.
- [Mission Control overview](https://help.splunk.com/en/splunk-enterprise-security-8/user-guide/8.6/mission-control/overview-of-mission-control-in-splunk-enterprise-security) — analyst workflow.
- [AWS Organizations input](https://help.splunk.com/en/data-management/ingest-data-from-cloud-sources/use-data-inputs/1.18/amazon-web-services-data/create-input-for-aws-organizations) and [AWS validated architecture](https://help.splunk.com/en/data-management/splunk-validated-architectures/getting-data-in-forwarding-and-preprocessing/getting-aws-data-into-the-splunk-platform) — AWS onboarding.
- [AWS Security Content detections](https://research.splunk.com/detections/platforms/aws/) — detection catalog.
- [Risk-based alerting](https://help.splunk.com/en/splunk-enterprise-security-8/user-guide/8.4/mission-control/analyze-risk-with-risk-based-alerting-in-splunk-enterprise-security) — risk model.
- [UEBA overview](https://help.splunk.com/en/splunk-enterprise-security-8/administer/8.5/user-and-entity-behavior-analytics/user-and-entity-behavior-analytics-ueba-overview-in-splunk-enterprise-security) — behavior analytics.
- [Threat intelligence overview](https://help.splunk.com/en/splunk-enterprise-security-8/administer/8.5/threat-intelligence/overview-of-threat-intelligence-in-splunk-enterprise-security) — feed and investigation support.
- [Pair Enterprise Security with SOAR](https://help.splunk.com/en/splunk-enterprise-security-8/administer/8.5/configuration-and-settings/pair-splunk-enterprise-security-with-splunk-soar) and [SOAR Cloud](https://help.splunk.com/en/splunk-soar/soar-cloud/use-soar-cloud/introduction/about-splunk-soar-cloud) — orchestration.
- [Splunk Attack Analyzer](https://www.splunk.com/en_us/products/attack-analyzer.html) — phishing/malware analysis.
- [Agentic AI offerings in ES](https://help.splunk.com/en/splunk-enterprise-security-8/administer/8.6/ai-assistant-in-security-and-agentic-capabilities/agentic-ai-offerings-in-splunk-enterprise-security) — current security agents and prerequisites.
- [Federated Analytics for Amazon Security Lake](https://help.splunk.com/en/splunk-cloud-platform/search/federated-search/10.5.2605/ingest-and-search-amazon-security-lake-datasets/about-federated-analytics) — OCSF/Security Lake design.

### Elastic and AWS implementation references

- [Monitor AWS with Elastic Agent](https://www.elastic.co/docs/solutions/observability/cloud/monitor-amazon-web-services-aws) and [AWS integration](https://www.elastic.co/docs/reference/integrations/aws) — AWS data collection.
- [AWS Firehose quickstart](https://www.elastic.co/docs/solutions/observability/get-started/quickstart-collect-data-with-aws-firehose) — low-latency onboarding path and constraints.
- [Elastic Cloud Forwarder for AWS](https://www.elastic.co/docs/reference/opentelemetry/edot-cloud-forwarder/aws) — AWS S3/CloudWatch forwarding.
- [Elastic OpenTelemetry](https://www.elastic.co/docs/reference/opentelemetry) and [OpenTelemetry on Kubernetes](https://www.elastic.co/docs/solutions/observability/get-started/opentelemetry/use-cases/kubernetes/deployment) — portable instrumentation.
- [Agent Builder custom tools](https://www.elastic.co/docs/explore-analyze/ai-features/agent-builder/tools/custom-tools), [ES|QL tools](https://www.elastic.co/docs/explore-analyze/ai-features/agent-builder/tools/esql-tools), and [agents with Workflows](https://www.elastic.co/docs/explore-analyze/ai-features/agent-builder/agents-and-workflows) — controlled agent design.
- [Observability Workflows](https://www.elastic.co/docs/explore-analyze/workflows/use-cases/observability), [AI-augmented Workflows](https://www.elastic.co/docs/explore-analyze/workflows/use-cases/ai-augmented-workflows), and [approval step](https://www.elastic.co/docs/explore-analyze/workflows/steps/wait-for-approval) — investigation and response.
- [Elastic Security for Cloud](https://www.elastic.co/docs/solutions/security/cloud) and [CNVM](https://www.elastic.co/docs/solutions/security/cloud/cloud-native-vulnerability-management) — cloud-security scope and constraints.
- [Entity risk scoring](https://www.elastic.co/guide/en/security/8.19/entity-risk-scoring.html), [Attack Discovery](https://www.elastic.co/docs/solutions/security/ai/attack-discovery), and [investigation tools](https://www.elastic.co/docs/solutions/security/investigate) — security investigation.
- [ES|QL detection rules](https://www.elastic.co/docs/solutions/security/detect-and-alert/esql) and [prebuilt security ML jobs](https://www.elastic.co/docs/reference/machine-learning/ootb-ml-jobs-siem) — deterministic and behavioral detections.
- [CloudWatch Metric Streams](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Metric-Streams.html) and [quick partner setup](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-metric-streams-QuickPartner.html) — common AWS transport and cost basis.

## Handoff for follow-on agents

For Azure and GCP implementation, start with
[Azure and GCP PoC parity handoff](CLOUD_POC_PARITY_HANDOFF.md). It records the
completed AWS reference commit, shared quality gates, cloud-specific work, and
the required delivery order.

Start from PR 12, not the legacy `AWS/` directory. Before implementation:

1. confirm whether the product decision is one Observability project or an Observability + Security deployment;
2. re-check current Elastic feature availability and license/region constraints;
3. select one differentiated scenario and its scorecard before adding resources;
4. keep every generated conclusion linked to raw evidence;
5. add tests and demo instructions in the same change as each capability;
6. update this document when a gap is closed, including the exact commit and verification result.
