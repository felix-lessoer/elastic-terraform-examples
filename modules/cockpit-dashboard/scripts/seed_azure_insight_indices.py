#!/usr/bin/env python3
"""Seed Observability insight indices for the Azure cockpit.

Mirrors Security KPIs + builds coverage/assets/events so the hub never depends
on broken CPS qualifiers / placeholder aliases.

Indices (Observability):
  azure-cockpit-security-kpi, azure-cockpit-coverage, azure-cockpit-assets,
  azure-cockpit-events
"""

from __future__ import annotations

import argparse

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
    recommendation_discover_href,
    scalar,
)

SECURITY_KPI = "azure-cockpit-security-kpi"
COVERAGE = "azure-cockpit-coverage"
ASSETS = "azure-cockpit-assets"
EVENTS = "azure-cockpit-events"

def _dash(did: str) -> str:
    return f"/app/dashboards#/view/{did}"


SERVICE_CATALOG = [
    {"service": "vm", "label": "Virtual Machines", "datasets": ["azure.compute_vm"], "category": "compute", "link": _dash("azure_metrics-eb3f05f0-ea9a-11e9-90ec-112a988266d5")},
    {"service": "storage", "label": "Storage Accounts", "datasets": ["azure.storage_account"], "category": "storage", "link": _dash("azure_metrics-1a151f80-32db-11ea-a83e-25b8612d00cc")},
    {"service": "aci", "label": "Container Instances", "datasets": ["azure.container_instance"], "category": "compute", "link": _dash("azure_metrics-9c11ac60-6cf6-11ea-8fe8-71add5fd7c38")},
    {"service": "billing", "label": "Billing", "datasets": ["azure.billing"], "category": "cost", "link": _dash("azure_billing-d3efeb30-c1c7-11ea-b7e7-0f48178cdb3c")},
    {"service": "activitylogs", "label": "Activity Logs", "datasets": ["azure.activitylogs"], "category": "security", "link": _dash("azure-41e84340-ec20-11e9-90ec-112a988266d5")},
    {"service": "platformlogs", "label": "Platform Logs", "datasets": ["azure.platformlogs"], "category": "platform", "link": _dash("azure-41e84340-ec20-11e9-90ec-112a988266d5")},
    {"service": "springcloud", "label": "Spring Cloud", "datasets": ["azure.springcloud"], "category": "compute", "link": "/app/fleet/integrations"},
    {"service": "app_service", "label": "App Service", "datasets": ["azure.app_service"], "category": "compute", "link": "/app/fleet/integrations"},
]

OPTIONAL = {"aci", "springcloud", "app_service", "billing"}


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

    activity = count_or_zero(
        sec_es,
        sec_user,
        sec_pass,
        "FROM logs-azure.activitylogs* | WHERE @timestamp > NOW() - 24 hours | STATS c = COUNT(*)",
    ) or count_or_zero(sec_es, sec_user, sec_pass, "FROM logs-azure.activitylogs* | STATS c = COUNT(*)")
    platform = count_or_zero(
        sec_es,
        sec_user,
        sec_pass,
        "FROM logs-azure.platformlogs* | WHERE @timestamp > NOW() - 24 hours | STATS c = COUNT(*)",
    ) or count_or_zero(sec_es, sec_user, sec_pass, "FROM logs-azure.platformlogs* | STATS c = COUNT(*)")
    doc = {
        "@timestamp": now_iso(),
        "kpi_id": "current",
        "active_alerts": int(active or 0),
        "high_critical_alerts": int(high or 0),
        "cspm_findings": max(int(cspm or 0), int(cspm_obs or 0)),
        "activity_24h": int(activity or 0),
        "platform_24h": int(platform or 0),
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
                    "metrics-azure.compute_vm*",
                    "metrics-azure.storage_account*",
                    "metrics-azure.container_instance*",
                    "metrics-azure.billing*",
                ],
            ),
            (
                sec_es,
                sec_user,
                sec_pass,
                ["logs-azure.activitylogs*", "logs-azure.platformlogs*"],
            ),
        ],
    )
    docs = build_coverage_docs(
        SERVICE_CATALOG,
        stats,
        optional_services=OPTIONAL,
        stale_after={"billing": 36, "activitylogs": 12},
    )
    bulk_index(obs_es, obs_user, obs_pass, COVERAGE, docs)
    healthy = sum(1 for _, d in docs if d["status"] == "healthy")
    print(f"  {COVERAGE}: {healthy}/{len(docs)} healthy services")


def seed_assets(obs_es, obs_user, obs_pass) -> None:
    ensure_index(obs_es, obs_user, obs_pass, ASSETS, ASSETS_MAPPINGS)
    ts = now_iso()
    docs: list[tuple[str, dict]] = []
    vms = esql(
        obs_es,
        obs_user,
        obs_pass,
        """FROM metrics-azure.compute_vm-default
| WHERE @timestamp > NOW() - 24 hours
| STATS avg_cpu = AVG(azure.compute_vm.percentage_cpu.avg), last_seen = MAX(@timestamp)
    BY cloud.instance.name, cloud.region, cloud.account.id, cloud.machine.type
| SORT avg_cpu ASC
| LIMIT 200""",
    )
    for row in vms:
        name = row.get("cloud.instance.name") or "unknown"
        docs.append(
            (
                f"vm-{name}",
                {
                    "@timestamp": ts,
                    "resource": {"type": "azure_vm", "name": name, "id": name},
                    "cloud": {
                        "region": row.get("cloud.region"),
                        "account": {"id": row.get("cloud.account.id")},
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
        """FROM metrics-azure.storage_account-default
| WHERE @timestamp > NOW() - 7 days
| STATS max_bytes = MAX(COALESCE(azure.storage_account.used_capacity.avg, azure.storage_account.used_capacity.total)), last_seen = MAX(@timestamp)
    BY account_name = COALESCE(azure.resource.name, azure.storage_account.name), cloud.region, cloud.account.id
| SORT max_bytes DESC
| LIMIT 300""",
    )
    for row in storage:
        name = row.get("account_name") or "unknown"
        docs.append(
            (
                f"sa-{name}",
                {
                    "@timestamp": ts,
                    "resource": {"type": "storage_account", "name": name, "id": name},
                    "cloud": {
                        "region": row.get("cloud.region"),
                        "account": {"id": row.get("cloud.account.id")},
                    },
                    "metric_name": "used_capacity_bytes",
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
    activity = esql(
        sec_es,
        sec_user,
        sec_pass,
        """FROM logs-azure.activitylogs*
| WHERE @timestamp > NOW() - 24 hours
| STATS c = COUNT(*) BY event.provider
| SORT c DESC
| LIMIT 8""",
    )
    if not activity:
        activity = esql(
            sec_es,
            sec_user,
            sec_pass,
            """FROM logs-azure.activitylogs*
| WHERE @timestamp > NOW() - 24 hours
| STATS c = COUNT(*) BY azure.activitylogs.operation_name
| SORT c DESC
| LIMIT 8""",
        )
    # Recommendations first (actionable)
    recs = esql(
        obs_es,
        obs_user,
        obs_pass,
        """FROM azure-cockpit-recommendations
| WHERE @timestamp > NOW() - 7 days
| STATS c = COUNT(*) BY severity, category
| SORT c DESC
| LIMIT 10""",
    )
    for row in recs:
        sev = row.get("severity") or "low"
        cat = row.get("category") or "insight"
        label = str(cat).replace("_", " ")
        docs.append(
            (
                f"rec-{sev}-{cat}",
                {
                    "@timestamp": ts,
                    "event.source": "cockpit.recommendations",
                    "event.severity": sev,
                    "event.category": cat,
                    "title": f"{int(row.get('c') or 0)} {label} recommendations",
                    "detail": f"Open Discover for {sev} {label} findings →",
                    "service": "recommendations",
                    "link": recommendation_discover_href(
                        "azure-cockpit-recommendations", category=str(cat), severity=str(sev)
                    ),
                },
            )
        )

    activity_dash = "/app/dashboards#/view/azure-41e84340-ec20-11e9-90ec-112a988266d5"
    for row in activity:
        provider = (
            row.get("event.provider")
            or row.get("azure.activitylogs.operation_name")
            or "azure.activitylogs"
        )
        docs.append(
            (
                f"activity-{abs(hash(str(provider))) % 10_000_000}",
                {
                    "@timestamp": ts,
                    "event.source": "azure.activitylogs",
                    "event.severity": "info",
                    "event.category": "api_activity",
                    "title": f"Activity: {provider}",
                    "detail": f"{int(row.get('c') or 0):,} activity events in the last 24h — open overview →",
                    "service": str(provider),
                    "link": activity_dash,
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
    print("Seeding Azure cockpit insight indices…")
    seed_security_kpi(obs_es, sec_es, args.obs_user, args.obs_password, args.sec_user, args.sec_password)
    seed_coverage(obs_es, sec_es, args.obs_user, args.obs_password, args.sec_user, args.sec_password)
    seed_assets(obs_es, args.obs_user, args.obs_password)
    seed_events(obs_es, sec_es, args.obs_user, args.obs_password, args.sec_user, args.sec_password)
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
