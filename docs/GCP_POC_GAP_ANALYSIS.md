# GCP PoC modernization gap analysis

## Target

The GCP PoC must provide the same safe, guided outcome as the AWS PoC while
retaining GCP-specific topology and permissions. The acceptance criteria live
in [CLOUD_POC_PARITY_HANDOFF.md](CLOUD_POC_PARITY_HANDOFF.md).

## Current foundation

- `examples/gcp` creates Security and Observability projects, Cross-Project
  Search, GCP log sinks and Pub/Sub, Fleet policies, two GCE agents, workflows,
  and the GCP cockpit.
- `modules/gcp-cloud` provisions collection resources and an exported collector
  service-account key.
- `seed_gcp_insight_indices.py` seeds KPI, coverage, asset, and event indices.
- Workflows cover assets, coverage, hosts, GKE, Cloud Run, and Cloud SQL.

## Prioritized gaps

### P0: trustworthy behavior

- GKE, Cloud Run, and Cloud SQL workflows can run while their metric streams
  are disabled. Workflow deployment and execution must follow explicit
  telemetry flags.
- Recommendation documents need stable resource keys, deterministic IDs,
  snapshot cleanup, evidence windows, and an explicit distinction between
  missing telemetry and observed inactivity.
- There are no GCP workflow contracts or cockpit saved-object tests.

### P1: discovery and collection

- There is no bounded Cloud Asset Inventory discovery, local manifest, or
  partial-result behavior.
- Existing sinks, topics, subscriptions, metrics scopes, and collectors are
  not reused before new resources are created.
- Fleet reconciliation is absent.
- Exported service-account JSON is stored in Terraform state. Federation or
  impersonation should replace it where supported; residual key use must be
  isolated and documented.

### P1: Insight Engine

- Resource-level manifest, candidate, dependency, finding, instrumentation,
  and summary indices are missing.
- Reference indices are not prepared as lookup indices.
- There is no deterministic recommendation backfill, ML keeper, final summary
  workflow, or bounded workflow tooling for agents.
- Coverage is based mainly on dataset presence rather than discovered
  resources and signal freshness.

### P2: customer experience

- GCP has no local guided UI, readable plan table, persisted operation state,
  or integrated discovery path.
- Optional visibility changes do not have candidate selection, cost/impact
  acknowledgement, validation, persisted rollback, or fixture tests.
- The cockpit lacks a prominent refreshed agent summary and complete GCP
  contract coverage.

## Delivery gates

1. Telemetry and workflow contracts are truthful and idempotent.
2. Read-only discovery emits a validated bounded manifest.
3. Existing telemetry paths are reused and every introduced resource has a
   cleanup owner.
4. Resource-level coverage and findings retain evidence, confidence,
   contradictions, missing telemetry, and stable keys.
5. The guided path keeps credentials local and separates discovery, paid
   telemetry enablement, and workload mutation.
6. Unit and contract tests pass; live workflows complete; cockpit exports have
   no missing references; a final Terraform plan reports no drift.

Azure infrastructure and multicloud consolidation are intentionally excluded
until these GCP gates pass.
