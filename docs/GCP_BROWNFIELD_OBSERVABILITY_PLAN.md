# GCP brownfield observability plan

## Safety boundary

Discovery is read-only and runs before Terraform changes customer telemetry.
It never reads secret values, enables APIs or paid security tiers, mutates a
workload, or stores a full manifest in Terraform state. Telemetry enablement
and optional visibility adapters are separate, explicit operations.

## Discovery contract

Use Cloud Asset Inventory as the primary inventory and bounded service APIs
for telemetry configuration that is not represented there.

The discovery runner must:

- allow-list operations and approved project scopes;
- apply retries, throttling, per-call timeouts, a total call budget, resource
  limits, and bounded concurrency;
- report progress before slow operations and retain useful partial results;
- record resource IDs, locations, state, labels, ownership hints, deployment
  metadata, service-account references, and control-plane relationships;
- inventory existing Logging sinks, Pub/Sub paths, log buckets, metrics
  scopes, alert policies, Trace, Profiler, Managed Service for Prometheus,
  OpenTelemetry collectors, SCC, and Event Threat Detection configuration;
- validate a versioned local manifest and return only its hash and summary to
  Terraform.

Initial resource coverage includes GCE and MIGs, disks, GKE, Cloud Run and
Functions, Cloud SQL, GCS, load balancers, API Gateway, Pub/Sub, BigQuery,
Spanner/Firestore, and Redis.

## Collection decisions

For every discovered service family:

1. Reuse customer-owned sinks, subscriptions, metrics, and collectors when
   compatible.
2. Detect and reject duplicate destinations.
3. Present permissions, expected GCP and Elastic cost, signal purpose,
   ownership, freshness, and cleanup before enablement.
4. Enable only inputs required by selected workflows or an explicitly broader
   collection profile.
5. Reconcile stale Fleet agents after apply.

Prefer workload identity federation or service-account impersonation over
exported JSON keys where Fleet supports it. If a key remains necessary, use a
dedicated least-privilege collector identity, keep it out of outputs and logs,
document rotation, and make destruction revoke it.

## Analysis outputs

The validated manifest feeds cloud-prefixed indices for resources, service
candidates, dependencies, coverage, assets, events, recommendations, findings,
instrumentation plans, and the final summary. Coverage compares discovered
resources against fresh metrics, logs, traces, profiles, owners, and
dependencies. Missing telemetry is `unknown`, never `healthy` or `unused`.

Dependencies retain evidence and confidence. Runtime traces and explicit
control-plane relationships outrank routing, flow, endpoint, request-ID, and
metric-correlation evidence.

## Optional visibility adapters

Adapters are offered only for named eligible resources. Each proposal states
cost and workload impact, snapshots original configuration, uses narrow
credentials, validates signal arrival, stores owner-only rollback state, and
supports idempotent rollback. Inactive or unsupported candidates are skipped
with a reason rather than mutated.

## Verification

Fixture tests cover successful, denied, throttled, empty, timeout, partial,
duplicate-path, deploy, rollback, and orphan-cleanup cases. Live verification
uses a reviewed saved plan, polls workflow executions, checks signal freshness
and lookup joins, exports the cockpit, exercises cleanup, and ends with a
zero-change Terraform plan.
