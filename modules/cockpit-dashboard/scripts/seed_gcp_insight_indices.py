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
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from insight_fabric_common import (
    ASSETS_MAPPINGS,
    COVERAGE_MAPPINGS,
    EVENTS_MAPPINGS,
    SECURITY_KPI_MAPPINGS,
    bulk_index,
    ensure_index,
    esql,
    now_iso,
    recommendation_discover_href,
    req,
    scalar,
)

SECURITY_KPI = "gcp-cockpit-security-kpi"
MANIFEST = "gcp-cockpit-manifest"
SERVICE_CANDIDATES = "gcp-cockpit-service-candidates"
DEPENDENCIES = "gcp-cockpit-dependencies"
COVERAGE = "gcp-cockpit-coverage"
ASSETS = "gcp-cockpit-assets"
EVENTS = "gcp-cockpit-events"
RECOMMENDATIONS = "gcp-cockpit-recommendations"
FINDINGS = "gcp-cockpit-findings"
INSTRUMENTATION_PLANS = "gcp-cockpit-instrumentation-plans"
INSIGHT_SUMMARY = "gcp-cockpit-insight-summary"

RESOURCE_MAPPINGS = {
    "@timestamp": {"type": "date"},
    "resource": {
        "properties": {
            "key": {"type": "keyword"},
            "type": {"type": "keyword"},
            "name": {"type": "keyword"},
            "id": {"type": "keyword"},
        }
    },
    "cloud": {
        "properties": {
            "provider": {"type": "keyword"},
            "region": {"type": "keyword"},
            "availability_zone": {"type": "keyword"},
            "project": {"properties": {"id": {"type": "keyword"}}},
            "account": {"properties": {"id": {"type": "keyword"}}},
        }
    },
    "service": {"type": "keyword"},
    "owner": {"type": "keyword"},
    "discovered_at": {"type": "date"},
    "manifest": {"type": "object", "enabled": False},
}

DERIVED_INDEX_MAPPINGS = {
    SERVICE_CANDIDATES: {
        "@timestamp": {"type": "date"},
        "candidate_id": {"type": "keyword"},
        "service": {"type": "keyword"},
        "project_id": {"type": "keyword"},
        "owner": {"type": "keyword"},
        "resource_count": {"type": "long"},
        "resource_keys": {"type": "keyword"},
    },
    DEPENDENCIES: {
        "@timestamp": {"type": "date"},
        "source": {"type": "keyword"},
        "target": {"type": "keyword"},
        "relationship": {"type": "keyword"},
        "evidence": {"type": "keyword"},
        "confidence": {"type": "double"},
    },
    RECOMMENDATIONS: {
        "@timestamp": {"type": "date"},
        "resource": RESOURCE_MAPPINGS["resource"],
        "cloud": RESOURCE_MAPPINGS["cloud"],
        "category": {"type": "keyword"},
        "severity": {"type": "keyword"},
        "confidence": {"type": "keyword"},
        "activity_status": {"type": "keyword"},
        "lookback_days": {"type": "integer"},
        "evidence_refs": {"type": "keyword"},
        "contradictory_evidence": {"type": "keyword"},
        "missing_telemetry": {"type": "keyword"},
        "expected_value": {"type": "keyword"},
        "safe_next_action": {"type": "text"},
        "metric_name": {"type": "keyword"},
        "metric_value": {"type": "double"},
        "threshold": {"type": "double"},
        "recommendation": {"type": "text"},
    },
    FINDINGS: {
        "@timestamp": {"type": "date"},
        "resource": RESOURCE_MAPPINGS["resource"],
        "cloud": RESOURCE_MAPPINGS["cloud"],
        "category": {"type": "keyword"},
        "severity": {"type": "keyword"},
        "evidence_refs": {"type": "keyword"},
        "lookback": {"type": "keyword"},
        "confidence": {"type": "keyword"},
        "contradictory_evidence": {"type": "keyword"},
        "missing_telemetry": {"type": "keyword"},
        "expected_value": {"type": "keyword"},
        "safe_next_action": {"type": "text"},
    },
    INSTRUMENTATION_PLANS: {
        "@timestamp": {"type": "date"},
        "resource": {"properties": {"key": {"type": "keyword"}}},
        "status": {"type": "keyword"},
        "signals": {"type": "keyword"},
        "safe_next_action": {"type": "text"},
    },
    INSIGHT_SUMMARY: {
        "@timestamp": {"type": "date"},
        "level": {"type": "keyword"},
        "priority": {"type": "keyword"},
        "headline": {"type": "keyword"},
        "summary": {"type": "keyword", "ignore_above": 8191},
        "action_1": {"type": "keyword", "ignore_above": 2048},
        "action_2": {"type": "keyword", "ignore_above": 2048},
        "action_3": {"type": "keyword", "ignore_above": 2048},
    },
}

COVERAGE_RESOURCE_MAPPINGS = {
    **COVERAGE_MAPPINGS,
    "resource": RESOURCE_MAPPINGS["resource"],
    "cloud": RESOURCE_MAPPINGS["cloud"],
    "discovered": {"type": "boolean"},
    "signals": {
        "properties": {
            signal: {
                "properties": {
                    "status": {"type": "keyword"},
                    "last_seen": {"type": "date"},
                    "freshness_hours": {"type": "double"},
                }
            }
            for signal in ("metrics", "logs", "traces", "profiles")
        }
    },
}

def _dash(did: str) -> str:
    return f"/app/dashboards#/view/{did}"


SERVICE_CATALOG = [
    {"service": "compute", "label": "Compute Engine", "datasets": ["gcp.compute"], "category": "compute", "link": _dash("gcp-f40ee870-5e4a-11ea-a4f6-717338406083")},
    {"service": "gke", "label": "GKE", "datasets": ["gcp.gke"], "category": "compute", "link": _dash("gcp-1ae960c0-f9f8-11eb-bc38-79936db7c106")},
    {"service": "cloudrun", "label": "Cloud Run", "datasets": ["gcp.cloudrun_metrics"], "category": "compute", "link": _dash("gcp-f40ee870-5e4a-11ea-a4f6-717338406083")},
    {"service": "storage", "label": "Cloud Storage", "datasets": ["gcp.storage"], "category": "storage", "link": _dash("gcp-ca401040-8e52-11ea-9fa6-4d675d5290dc")},
    {"service": "cloudsql", "label": "Cloud SQL", "datasets": ["gcp.cloudsql_postgresql", "gcp.cloudsql_mysql"], "category": "data", "link": _dash("gcp-ddc19780-3a0a-11ee-8736-83dacf143f01")},
    {"service": "pubsub", "label": "Pub/Sub", "datasets": ["gcp.pubsub"], "category": "platform", "link": _dash("gcp-2b0fd7b0-feac-11ea-b032-d59f894a5072")},
    {"service": "firestore", "label": "Firestore", "datasets": ["gcp.firestore"], "category": "data", "link": "/app/fleet/integrations"},
    {"service": "dataproc", "label": "Dataproc", "datasets": ["gcp.dataproc"], "category": "compute", "link": "/app/fleet/integrations"},
    {"service": "redis", "label": "Memorystore for Redis", "datasets": ["gcp.redis"], "category": "data", "link": "/app/fleet/integrations"},
    {"service": "loadbalancing", "label": "Load Balancing", "datasets": ["gcp.loadbalancing_metrics", "gcp.loadbalancing_logs"], "category": "network", "link": _dash("gcp-aa5b8bd0-9157-11ea-8180-7b0dacd9df87")},
    {"service": "vpcflow", "label": "VPC Flow", "datasets": ["gcp.vpcflow"], "category": "network", "link": _dash("gcp-9484a4cd-685f-450e-aeaa-728fbdbea20f")},
    {"service": "dns", "label": "Cloud DNS", "datasets": ["gcp.dns"], "category": "network", "link": "/app/fleet/integrations"},
    {"service": "billing", "label": "Billing", "datasets": ["gcp.billing"], "category": "cost", "link": _dash("gcp-76c9e920-e890-11ea-bf8c-d13ebf358a78")},
    {"service": "audit", "label": "Audit Logs", "datasets": ["gcp.audit"], "category": "security", "link": _dash("gcp-48e12760-cbe4-11ec-b519-85ccf621cbbf")},
    {"service": "firewall", "label": "Firewall", "datasets": ["gcp.firewall"], "category": "security", "link": _dash("gcp-8a1fb690-cbeb-11ec-b519-85ccf621cbbf")},
]

OPTIONAL = {"dns", "billing"}


def _slug(value: object) -> str:
    return str(value or "unknown").strip().lower().replace("/", "_").replace(" ", "_")


def _identity(value: object) -> str:
    return str(value or "").strip().rstrip("/").rsplit("/", 1)[-1].lower()


def resource_key(resource: dict[str, Any]) -> str:
    project = (
        resource.get("project_id")
        or resource.get("account_id")
        or resource.get("project")
        or "unknown-project"
    )
    region = (
        resource.get("region")
        or resource.get("zone")
        or resource.get("location")
        or "global"
    )
    resource_type = _resource_type(resource)
    resource_id = (
        resource.get("id")
        or resource.get("resource_id")
        or resource.get("name")
        or resource.get("self_link")
        or resource.get("url")
        or "unknown"
    )
    return canonical_resource_key(project, region, resource_type, resource_id)


def _service_for(resource: dict[str, Any]) -> str:
    explicit = resource.get("service") or resource.get("service_name")
    if explicit:
        return _slug(explicit)
    resource_type = str(
        resource.get("type")
        or resource.get("resource_type")
        or resource.get("asset_type")
        or resource.get("kind")
        or ""
    )
    aliases = {
        "compute": "compute",
        "container": "gke",
        "kubernetes": "gke",
        "cloud_run": "cloudrun",
        "run.googleapis": "cloudrun",
        "storage": "storage",
        "sql": "cloudsql",
        "pubsub": "pubsub",
        "firestore": "firestore",
        "dataproc": "dataproc",
        "redis": "redis",
        "loadbalanc": "loadbalancing",
        "dns": "dns",
        "firewall": "firewall",
    }
    lowered = resource_type.lower()
    return next((service for marker, service in aliases.items() if marker in lowered), _slug(resource_type))


def _resource_type(resource: dict[str, Any]) -> str:
    value = _slug(
        resource.get("type")
        or resource.get("resource_type")
        or resource.get("asset_type")
        or resource.get("kind")
    )
    aliases = {
        "google_compute_instance": "gce_instance",
        "gcp.compute.instance": "gce_instance",
        "compute.googleapis.com_instance": "gce_instance",
        "google_storage_bucket": "gcs_bucket",
        "gcp.storage.bucket": "gcs_bucket",
        "storage.googleapis.com_bucket": "gcs_bucket",
        "google_container_cluster": "gke_cluster",
        "google_cloud_run_v2_service": "cloud_run_service",
        "google_sql_database_instance": "cloud_sql_instance",
        "sqladmin.googleapis.com_instance": "cloud_sql_instance",
        "container.googleapis.com_cluster": "gke_cluster",
        "run.googleapis.com_service": "cloud_run_service",
        "firestore.googleapis.com_database": "firestore_database",
        "dataproc.googleapis.com_cluster": "dataproc_cluster",
        "redis.googleapis.com_instance": "redis_instance",
    }
    return aliases.get(value, value)


def canonical_resource_key(
    project: object, region: object, resource_type: str, resource_id: object
) -> str:
    return ":".join(
        _slug(value)
        for value in (
            project or "unknown-project",
            region or "global",
            resource_type,
            resource_id,
        )
    )


def load_manifest(path: str) -> dict[str, Any]:
    if not path:
        return {}
    manifest_path = Path(path)
    if not manifest_path.exists():
        raise FileNotFoundError(f"GCP manifest does not exist: {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    if not isinstance(manifest, dict) or not isinstance(manifest.get("resources", []), list):
        raise ValueError("GCP manifest must be an object with a resources array")
    return manifest


def manifest_documents(
    manifest: dict[str, Any], timestamp: str
) -> tuple[
    list[tuple[str, dict]], list[tuple[str, dict]], list[tuple[str, dict]]
]:
    """Build raw resource, service-candidate, and explicit dependency documents."""
    raw_docs: list[tuple[str, dict]] = []
    dependencies: list[tuple[str, dict]] = []
    candidates: dict[tuple[str, str, str], list[str]] = {}
    discovered_at = manifest.get("discovered_at") or manifest.get("generated_at") or timestamp
    for resource in manifest.get("resources", []):
        if not isinstance(resource, dict):
            continue
        key = resource_key(resource)
        project = str(
            resource.get("project_id")
            or resource.get("account_id")
            or resource.get("project")
            or "unknown-project"
        )
        service = _service_for(resource)
        owner = str(
            resource.get("owner")
            or (resource.get("labels") or {}).get("owner")
            or next(iter((resource.get("ownership_hints") or {}).values()), None)
            or "unknown"
        )
        resource_id = str(
            resource.get("id")
            or resource.get("resource_id")
            or resource.get("name")
            or resource.get("self_link")
            or "unknown"
        )
        raw_docs.append(
            (
                hashlib.sha256(key.encode()).hexdigest(),
                {
                    "@timestamp": timestamp,
                    "resource": {
                        "key": key,
                        "type": _resource_type(resource),
                        "name": resource.get("display_name") or resource.get("name") or resource_id,
                        "id": resource_id,
                    },
                    "cloud": {
                        "provider": "gcp",
                        "region": resource.get("region") or resource.get("location"),
                        "availability_zone": resource.get("zone"),
                        "project": {"id": project},
                        "account": {"id": project},
                    },
                    "service": service,
                    "owner": owner,
                    "discovered_at": discovered_at,
                    "manifest": resource,
                },
            )
        )
        candidates.setdefault((service, project, owner), []).append(key)
        relationships = resource.get("dependencies") or resource.get("relationships") or []
        for relationship in relationships:
            if isinstance(relationship, str):
                target, relationship_type, evidence, confidence = (
                    relationship,
                    "depends_on",
                    "manifest",
                    1.0,
                )
            elif isinstance(relationship, dict):
                target = (
                    relationship.get("target_key")
                    or relationship.get("target")
                    or relationship.get("resource_key")
                )
                relationship_type = relationship.get("type") or "depends_on"
                evidence = relationship.get("evidence") or "manifest"
                confidence = relationship.get("confidence", 1.0)
            else:
                continue
            if not target:
                continue
            dep_id = hashlib.sha256(f"{key}:{relationship_type}:{target}".encode()).hexdigest()
            dependencies.append(
                (
                    dep_id,
                    {
                        "@timestamp": timestamp,
                        "source": key,
                        "target": str(target),
                        "relationship": str(relationship_type),
                        "evidence": str(evidence),
                        "confidence": float(confidence),
                    },
                )
            )
    candidate_docs = []
    for (service, project, owner), keys in sorted(candidates.items()):
        candidate_id = f"{project}:{service}:{owner}"
        candidate_docs.append(
            (
                hashlib.sha256(candidate_id.encode()).hexdigest(),
                {
                    "@timestamp": timestamp,
                    "candidate_id": candidate_id,
                    "service": service,
                    "project_id": project,
                    "owner": owner,
                    "resource_count": len(keys),
                    "resource_keys": sorted(keys),
                },
            )
        )
    return raw_docs, candidate_docs, dependencies


def _freshness(last_seen: object, *, stale_after_hours: float = 8) -> dict:
    if not last_seen:
        return {"status": "unknown", "last_seen": None, "freshness_hours": None}
    try:
        if isinstance(last_seen, (int, float)):
            age = (time.time() * 1000 - float(last_seen)) / 3_600_000
        else:
            age = (
                datetime.now(timezone.utc)
                - datetime.fromisoformat(str(last_seen).replace("Z", "+00:00"))
            ).total_seconds() / 3600
    except (TypeError, ValueError):
        return {"status": "unknown", "last_seen": None, "freshness_hours": None}
    return {
        "status": "fresh" if age <= stale_after_hours else "stale",
        "last_seen": last_seen,
        "freshness_hours": max(age, 0),
    }


def clear_snapshot(es: str, user: str, password: str, index: str) -> None:
    try:
        req(
            "POST",
            f"{es}/{index}/_delete_by_query?conflicts=proceed&refresh=true",
            user,
            password,
            {"query": {"match_all": {}}},
        )
    except RuntimeError as exc:
        print(f"  {index} snapshot cleanup warning: {exc}", file=sys.stderr)


def build_resource_coverage_docs(
    manifest_docs: list[tuple[str, dict]],
    asset_docs: list[tuple[str, dict]],
    timestamp: str,
) -> list[tuple[str, dict]]:
    """Compare every discovered resource with observed signals.

    Missing evidence is represented as ``unknown``; it is never interpreted as
    an unused resource or as healthy coverage.
    """
    observed = {
        doc["resource"].get("key"): doc
        for _, doc in asset_docs
        if doc.get("resource", {}).get("key")
    }
    observed_by_identity = {}
    for _, doc in asset_docs:
        resource = doc.get("resource", {})
        cloud = doc.get("cloud", {})
        project = (
            (cloud.get("project") or {}).get("id")
            or (cloud.get("account") or {}).get("id")
        )
        for identity in (resource.get("id"), resource.get("name")):
            if identity:
                observed_by_identity[
                    (_slug(project), resource.get("type"), _identity(identity))
                ] = doc
    discovered = list(manifest_docs) or [
        (doc_id, {**doc, "service": _service_for(doc.get("resource", {}))})
        for doc_id, doc in asset_docs
    ]
    docs = []
    for _, resource_doc in discovered:
        resource = resource_doc["resource"]
        key = resource["key"]
        observed_doc = observed.get(key)
        if not observed_doc:
            cloud = resource_doc.get("cloud", {})
            project = (
                (cloud.get("project") or {}).get("id")
                or (cloud.get("account") or {}).get("id")
            )
            for identity in (resource.get("name"), resource.get("id")):
                candidate = observed_by_identity.get(
                    (
                        _slug(project),
                        resource.get("type"),
                        _identity(identity),
                    )
                )
                if candidate:
                    observed_doc = candidate
                    break
        metrics = _freshness(
            observed_doc.get("last_seen")
            if observed_doc and observed_doc.get("metric_name") != "inventory_only"
            else None
        )
        signals = {
            "metrics": metrics,
            "logs": {"status": "unknown", "last_seen": None, "freshness_hours": None},
            "traces": {"status": "unknown", "last_seen": None, "freshness_hours": None},
            "profiles": {"status": "unknown", "last_seen": None, "freshness_hours": None},
        }
        declared = (resource_doc.get("manifest") or {}).get("signals") or {}
        for signal in signals:
            value = declared.get(signal)
            if isinstance(value, dict):
                signals[signal] = _freshness(value.get("last_seen"))
            elif value:
                signals[signal] = {"status": "unknown", "last_seen": None, "freshness_hours": None}
        known = [value["status"] for value in signals.values() if value["status"] != "unknown"]
        status = "unknown" if not known else ("stale" if "stale" in known else "healthy")
        detail = "signal data unavailable" if status == "unknown" else f"metrics {metrics['status']}"
        service = resource_doc.get("service") or _service_for(resource)
        docs.append(
            (
                hashlib.sha256(key.encode()).hexdigest(),
                {
                    "@timestamp": timestamp,
                    "resource": resource,
                    "cloud": resource_doc.get("cloud", {}),
                    "service": service,
                    "label": resource.get("name") or resource.get("id"),
                    "category": next(
                        (
                            item["category"]
                            for item in SERVICE_CATALOG
                            if item["service"] == service
                        ),
                        "other",
                    ),
                    "status": status,
                    "docs_24h": 0,
                    "last_seen": metrics["last_seen"],
                    "datasets": [],
                    "detail": detail,
                    "link": "/app/discover",
                    "discovered": True,
                    "signals": signals,
                },
            )
        )
    return docs


def seed_manifest_fabric(
    obs_es: str,
    obs_user: str,
    obs_pass: str,
    manifest: dict[str, Any],
) -> list[tuple[str, dict]]:
    timestamp = now_iso()
    manifest_docs, candidate_docs, dependency_docs = manifest_documents(manifest, timestamp)
    ensure_index(obs_es, obs_user, obs_pass, MANIFEST, RESOURCE_MAPPINGS)
    clear_snapshot(obs_es, obs_user, obs_pass, MANIFEST)
    bulk_index(obs_es, obs_user, obs_pass, MANIFEST, manifest_docs)
    for index, docs in (
        (SERVICE_CANDIDATES, candidate_docs),
        (DEPENDENCIES, dependency_docs),
    ):
        ensure_index(obs_es, obs_user, obs_pass, index, DERIVED_INDEX_MAPPINGS[index])
        clear_snapshot(obs_es, obs_user, obs_pass, index)
        bulk_index(obs_es, obs_user, obs_pass, index, docs)
    for index in (
        RECOMMENDATIONS,
        FINDINGS,
        INSTRUMENTATION_PLANS,
        INSIGHT_SUMMARY,
    ):
        ensure_index(obs_es, obs_user, obs_pass, index, DERIVED_INDEX_MAPPINGS[index])
    print(
        f"  {MANIFEST}: {len(manifest_docs)} resources, "
        f"{len(candidate_docs)} service candidates, {len(dependency_docs)} dependencies"
    )
    return manifest_docs


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


def seed_coverage(
    obs_es,
    obs_user,
    obs_pass,
    manifest_docs: list[tuple[str, dict]],
    asset_docs: list[tuple[str, dict]],
) -> None:
    ensure_index(obs_es, obs_user, obs_pass, COVERAGE, COVERAGE_RESOURCE_MAPPINGS)
    docs = build_resource_coverage_docs(manifest_docs, asset_docs, now_iso())
    clear_snapshot(obs_es, obs_user, obs_pass, COVERAGE)
    bulk_index(obs_es, obs_user, obs_pass, COVERAGE, docs)
    healthy = sum(1 for _, d in docs if d["status"] == "healthy")
    unknown = sum(1 for _, d in docs if d["status"] == "unknown")
    print(f"  {COVERAGE}: {healthy}/{len(docs)} healthy resources, {unknown} unknown")


def seed_assets(
    obs_es,
    obs_user,
    obs_pass,
    manifest_docs: list[tuple[str, dict]] | None = None,
) -> list[tuple[str, dict]]:
    mappings = {
        **ASSETS_MAPPINGS,
        "resource": {
            "properties": {
                **ASSETS_MAPPINGS["resource"]["properties"],
                "key": {"type": "keyword"},
            }
        },
    }
    ensure_index(obs_es, obs_user, obs_pass, ASSETS, mappings)
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
                    "resource": {
                        "type": "gce_instance",
                        "name": name,
                        "id": rid,
                        "key": canonical_resource_key(
                            row.get("cloud.account.id"),
                            row.get("cloud.region") or row.get("cloud.availability_zone"),
                            "gce_instance",
                            rid,
                        ),
                    },
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
                    "resource": {
                        "type": "gcs_bucket",
                        "name": name,
                        "id": name,
                        "key": canonical_resource_key(
                            row.get("cloud.account.id"),
                            row.get("gcp.labels.resource.location"),
                            "gcs_bucket",
                            name,
                        ),
                    },
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
    observed_keys = {doc["resource"]["key"] for _, doc in docs}
    for doc_id, manifest_doc in manifest_docs or []:
        if manifest_doc["resource"]["key"] in observed_keys:
            continue
        docs.append(
            (
                f"manifest-{doc_id}",
                {
                    "@timestamp": ts,
                    "resource": manifest_doc["resource"],
                    "cloud": manifest_doc["cloud"],
                    "metric_name": "inventory_only",
                    "metric_value": 0,
                    "last_seen": manifest_doc.get("discovered_at") or ts,
                },
            )
        )
    clear_snapshot(obs_es, obs_user, obs_pass, ASSETS)
    bulk_index(obs_es, obs_user, obs_pass, ASSETS, docs)
    print(f"  {ASSETS}: {len(docs)} resources")
    return docs


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
    # Recommendations first (actionable)
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
                        "gcp-cockpit-recommendations", category=str(cat), severity=str(sev)
                    ),
                },
            )
        )

    audit_dash = "/app/dashboards#/view/gcp-48e12760-cbe4-11ec-b519-85ccf621cbbf"
    fw_dash = "/app/dashboards#/view/gcp-8a1fb690-cbeb-11ec-b519-85ccf621cbbf"
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
                    "detail": f"{count:,} audit events in the last 24h — open Audit dashboard →",
                    "service": str(provider),
                    "link": audit_dash,
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
                    "detail": f"{int(row.get('c') or 0):,} firewall events (24h) — open Firewall dashboard →",
                    "service": "firewall",
                    "link": fw_dash,
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
    p.add_argument(
        "--manifest",
        default="",
        help="Validated GCP discovery manifest to ingest before deriving coverage",
    )
    args = p.parse_args()
    obs_es = args.obs_es.rstrip("/")
    sec_es = args.sec_es.rstrip("/")
    print("Seeding GCP cockpit insight indices…")
    manifest = load_manifest(args.manifest)
    manifest_docs = seed_manifest_fabric(
        obs_es, args.obs_user, args.obs_password, manifest
    )
    seed_security_kpi(obs_es, sec_es, args.obs_user, args.obs_password, args.sec_user, args.sec_password)
    asset_docs = seed_assets(
        obs_es,
        args.obs_user,
        args.obs_password,
        manifest_docs,
    )
    seed_coverage(
        obs_es,
        args.obs_user,
        args.obs_password,
        manifest_docs,
        asset_docs,
    )
    seed_events(obs_es, sec_es, args.obs_user, args.obs_password, args.sec_user, args.sec_password)
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
