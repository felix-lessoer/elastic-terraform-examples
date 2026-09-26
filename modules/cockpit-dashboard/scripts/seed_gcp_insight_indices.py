#!/usr/bin/env python3
"""Seed Observability insight indices for the GCP cockpit.

Mirrors Security KPIs + builds coverage/assets/events so the hub never depends
on broken CPS qualifiers.

Indices (Observability):
  gcp-cockpit-security-kpi, gcp-cockpit-coverage, gcp-cockpit-assets,
  gcp-cockpit-events
"""

from __future__ import annotations

import argparse
import sys

from insight_fabric_common import (
    ASSETS_MAPPINGS,
    COVERAGE_MAPPINGS,
    EVENTS_MAPPINGS,
    SECURITY_KPI_MAPPINGS,
    build_coverage_docs,
    bulk_index,
    collect_dataset_stats,
    ensure_index,
    esql,
    now_iso,
    scalar,
)

SECURITY_KPI = "gcp-cockpit-security-kpi"
COVERAGE = "gcp-cockpit-coverage"
ASSETS = "gcp-cockpit-assets"
EVENTS = "gcp-cockpit-events"

SERVICE_CATALOG = [
    {"service": "compute", "label": "Compute Engine", "datasets": ["gcp.compute"], "category": "compute"},
    {"service": "gke", "label": "GKE", "datasets": ["gcp.gke"], "category": "compute"},
    {"service": "cloudrun", "label": "Cloud Run", "datasets": ["gcp.cloudrun_metrics"], "category": "compute"},
    {"service": "storage", "label": "Cloud Storage", "datasets": ["gcp.storage"], "category": "storage"},
    {"service": "cloudsql", "label": "Cloud SQL", "datasets": ["gcp.cloudsql_postgresql", "gcp.cloudsql_mysql"], "category": "data"},
    {"service": "pubsub", "label": "Pub/Sub", "datasets": ["gcp.pubsub"], "category": "platform"},
    {"service": "loadbalancing", "label": "Load Balancing", "datasets": ["gcp.loadbalancing_metrics", "gcp.loadbalancing_logs"], "category": "network"},
    {"service": "vpcflow", "label": "VPC Flow", "datasets": ["gcp.vpcflow"], "category": "network"},
    {"service": "dns", "label": "Cloud DNS", "datasets": ["gcp.dns"], "category": "network"},
    {"service": "billing", "label": "Billing", "datasets": ["gcp.billing"], "category": "cost"},
    {"service": "audit", "label": "Audit Logs", "datasets": ["gcp.audit"], "category": "security"},
    {"service": "firewall", "label": "Firewall", "datasets": ["gcp.firewall"], "category": "security"},
]

OPTIONAL = {"dns", "billing"}


def seed_security_kpi(obs_es, sec_es, obs_user, obs_pass, sec_user, sec_pass) -> None:
    ensure_index(obs_es, obs_user, obs_pass, SECURITY_KPI, SECURITY_KPI_MAPPINGS)
    active = scalar(
        esql(
            sec_es,
            sec_user,
            sec_pass,
            'FROM .alerts-security.alerts-default | WHERE kibana.alert.status == "active" | STATS c = COUNT(*)',
        )
    )
    high = scalar(
        esql(
            sec_es,
            sec_user,
            sec_pass,
            'FROM .alerts-security.alerts-default | WHERE kibana.alert.status == "active" AND kibana.alert.severity IN ("high", "critical") | STATS c = COUNT(*)',
        )
    )
    cspm = scalar(
        esql(
            sec_es,
            sec_user,
            sec_pass,
            "FROM security_solution-cloud_security_posture.misconfiguration_latest | STATS c = COUNT(*)",
        )
    )
    cspm_obs = scalar(
        esql(
            obs_es,
            obs_user,
            obs_pass,
            "FROM security_solution-*.misconfiguration_latest | STATS c = COUNT(*)",
        )
    )

    def count_or_zero(es, user, pw, q):
        return int(scalar(esql(es, user, pw, q)) or 0)

    audit = count_or_zero(
        sec_es,
        sec_user,
        sec_pass,
        "FROM logs-gcp.audit* | WHERE @timestamp > NOW() - 24 hours | STATS c = COUNT(*)",
    ) or count_or_zero(sec_es, sec_user, sec_pass, "FROM logs-gcp.audit* | STATS c = COUNT(*)")
    firewall = count_or_zero(
        sec_es,
        sec_user,
        sec_pass,
        "FROM logs-gcp.firewall* | WHERE @timestamp > NOW() - 24 hours | STATS c = COUNT(*)",
    ) or count_or_zero(sec_es, sec_user, sec_pass, "FROM logs-gcp.firewall* | STATS c = COUNT(*)")
    doc = {
        "@timestamp": now_iso(),
        "kpi_id": "current",
        "active_alerts": int(active or 0),
        "high_critical_alerts": int(high or 0),
        "cspm_findings": max(int(cspm or 0), int(cspm_obs or 0)),
        "audit_24h": int(audit or 0),
        "firewall_24h": int(firewall or 0),
    }
    bulk_index(obs_es, obs_user, obs_pass, SECURITY_KPI, [("current", doc)])
    print(f"  {SECURITY_KPI}: {doc}")


def seed_coverage(obs_es, sec_es, obs_user, obs_pass, sec_user, sec_pass) -> None:
    ensure_index(obs_es, obs_user, obs_pass, COVERAGE, COVERAGE_MAPPINGS)
    stats = collect_dataset_stats(
        obs_es,
        sec_es,
        obs_user,
        obs_pass,
        sec_user,
        sec_pass,
        [
            (
                obs_es,
                obs_user,
                obs_pass,
                [
                    "metrics-gcp.compute*",
                    "metrics-gcp.gke*",
                    "metrics-gcp.cloudrun*",
                    "metrics-gcp.storage*",
                    "metrics-gcp.cloudsql*",
                    "metrics-gcp.pubsub*",
                    "metrics-gcp.loadbalancing*",
                    "logs-gcp.vpcflow*",
                    "logs-gcp.loadbalancing*",
                    "metrics-gcp.billing*",
                ],
            ),
            (
                sec_es,
                sec_user,
                sec_pass,
                ["logs-gcp.audit*", "logs-gcp.firewall*", "logs-gcp.dns*"],
            ),
        ],
    )
    docs = build_coverage_docs(
        SERVICE_CATALOG,
        stats,
        optional_services=OPTIONAL,
        stale_after={"billing": 36, "vpcflow": 24, "audit": 12},
    )
    bulk_index(obs_es, obs_user, obs_pass, COVERAGE, docs)
    healthy = sum(1 for _, d in docs if d["status"] == "healthy")
    print(f"  {COVERAGE}: {healthy}/{len(docs)} healthy services")


def seed_assets(obs_es, obs_user, obs_pass) -> None:
    ensure_index(obs_es, obs_user, obs_pass, ASSETS, ASSETS_MAPPINGS)
    ts = now_iso()
    docs: list[tuple[str, dict]] = []
    compute = esql(
        obs_es,
        obs_user,
        obs_pass,
        """FROM metrics-gcp.compute-default
| WHERE @timestamp > NOW() - 24 hours
| STATS avg_cpu = AVG(gcp.compute.instance.cpu.usage.pct), last_seen = MAX(@timestamp)
    BY cloud.instance.id, cloud.instance.name, cloud.availability_zone, cloud.region, cloud.account.id, cloud.machine.type
| SORT avg_cpu ASC
| LIMIT 200""",
    )
    for row in compute:
        rid = row.get("cloud.instance.id") or row.get("cloud.instance.name") or "unknown"
        name = row.get("cloud.instance.name") or rid
        docs.append(
            (
                f"gce-{rid}",
                {
                    "@timestamp": ts,
                    "resource": {"type": "gce_instance", "name": name, "id": rid},
                    "cloud": {
                        "region": row.get("cloud.region"),
                        "availability_zone": row.get("cloud.availability_zone"),
                        "account": {"id": row.get("cloud.account.id")},
                        "project": {"id": row.get("cloud.account.id")},
                        "machine": {"type": row.get("cloud.machine.type")},
                    },
                    "metric_name": "cpu_avg_24h",
                    "metric_value": row.get("avg_cpu") or 0,
                    "last_seen": row.get("last_seen"),
                },
            )
        )
    storage = esql(
        obs_es,
        obs_user,
        obs_pass,
        """FROM metrics-gcp.storage-default
| WHERE @timestamp > NOW() - 7 days
| STATS max_bytes = MAX(gcp.storage.storage.total.bytes), last_seen = MAX(@timestamp)
    BY gcp.labels.resource.bucket_name, gcp.labels.resource.location, cloud.account.id
| SORT max_bytes DESC
| LIMIT 300""",
    )
    for row in storage:
        name = row.get("gcp.labels.resource.bucket_name") or "unknown"
        docs.append(
            (
                f"gcs-{name}",
                {
                    "@timestamp": ts,
                    "resource": {"type": "gcs_bucket", "name": name, "id": name},
                    "cloud": {
                        "region": row.get("gcp.labels.resource.location"),
                        "account": {"id": row.get("cloud.account.id")},
                        "project": {"id": row.get("cloud.account.id")},
                    },
                    "metric_name": "bucket_size_bytes",
                    "metric_value": row.get("max_bytes") or 0,
                    "last_seen": row.get("last_seen"),
                },
            )
        )
    bulk_index(obs_es, obs_user, obs_pass, ASSETS, docs)
    print(f"  {ASSETS}: {len(docs)} resources")


def seed_events(obs_es, sec_es, obs_user, obs_pass, sec_user, sec_pass) -> None:
    ensure_index(obs_es, obs_user, obs_pass, EVENTS, EVENTS_MAPPINGS)
    docs: list[tuple[str, dict]] = []
    ts = now_iso()
    audit = esql(
        sec_es,
        sec_user,
        sec_pass,
        """FROM logs-gcp.audit*
| WHERE @timestamp > NOW() - 24 hours
| STATS c = COUNT(*) BY event.provider
| SORT c DESC
| LIMIT 8""",
    )
    if not audit:
        audit = esql(
            sec_es,
            sec_user,
            sec_pass,
            """FROM logs-gcp.audit*
| WHERE @timestamp > NOW() - 24 hours
| STATS c = COUNT(*) BY service.name
| SORT c DESC
| LIMIT 8""",
        )
    for row in audit:
        provider = row.get("event.provider") or row.get("service.name") or "gcp.audit"
        count = int(row.get("c") or 0)
        docs.append(
            (
                f"audit-{provider}",
                {
                    "@timestamp": ts,
                    "event.source": "gcp.audit",
                    "event.severity": "info",
                    "event.category": "api_activity",
                    "title": f"Audit: {provider}",
                    "detail": f"{count:,} audit events in the last 24h",
                    "service": str(provider),
                    "link": "/app/dashboards",
                },
            )
        )
    fw = esql(
        sec_es,
        sec_user,
        sec_pass,
        """FROM logs-gcp.firewall*
| WHERE @timestamp > NOW() - 24 hours
| STATS c = COUNT(*) BY event.action
| SORT c DESC
| LIMIT 5""",
    )
    for row in fw:
        action = row.get("event.action") or "firewall"
        docs.append(
            (
                f"firewall-{action}",
                {
                    "@timestamp": ts,
                    "event.source": "gcp.firewall",
                    "event.severity": "medium" if str(action).lower() in ("denied", "deny") else "info",
                    "event.category": "network",
                    "title": f"Firewall: {action}",
                    "detail": f"{int(row.get('c') or 0):,} firewall events (24h)",
                    "service": "firewall",
                    "link": "/app/dashboards",
                },
            )
        )
    recs = esql(
        obs_es,
        obs_user,
        obs_pass,
        """FROM gcp-cockpit-recommendations
| WHERE @timestamp > NOW() - 7 days
| STATS c = COUNT(*) BY severity, category
| SORT c DESC
| LIMIT 10""",
    )
    for row in recs:
        sev = row.get("severity") or "low"
        cat = row.get("category") or "insight"
        docs.append(
            (
                f"rec-{sev}-{cat}",
                {
                    "@timestamp": ts,
                    "event.source": "cockpit.recommendations",
                    "event.severity": sev,
                    "event.category": cat,
                    "title": f"{int(row.get('c') or 0)} {sev} {cat} recommendations",
                    "detail": "From scheduled GCP recommendation workflows",
                    "service": "recommendations",
                    "link": "#gcp-recommendations",
                },
            )
        )
    bulk_index(obs_es, obs_user, obs_pass, EVENTS, docs)
    print(f"  {EVENTS}: {len(docs)} events")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--obs-es", required=True)
    p.add_argument("--sec-es", required=True)
    p.add_argument("--obs-user", default="admin")
    p.add_argument("--sec-user", default="admin")
    p.add_argument("--obs-password", required=True)
    p.add_argument("--sec-password", required=True)
    args = p.parse_args()
    obs_es = args.obs_es.rstrip("/")
    sec_es = args.sec_es.rstrip("/")
    print("Seeding GCP cockpit insight indices…")
    seed_security_kpi(obs_es, sec_es, args.obs_user, args.obs_password, args.sec_user, args.sec_password)
    seed_coverage(obs_es, sec_es, args.obs_user, args.obs_password, args.sec_user, args.sec_password)
    seed_assets(obs_es, args.obs_user, args.obs_password)
    seed_events(obs_es, sec_es, args.obs_user, args.obs_password, args.sec_user, args.sec_password)
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
