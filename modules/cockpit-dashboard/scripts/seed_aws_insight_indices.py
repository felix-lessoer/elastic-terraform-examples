#!/usr/bin/env python3
"""Seed Observability insight indices for the AWS cockpit.

Cross-project bridge: reads Security + Observability Elasticsearch and writes
denormalized docs into Observability so the hub dashboard never depends on
broken CPS qualifiers.

Indices written (Observability):
  - aws-cockpit-security-kpi   single rolling summary for top KPIs
  - aws-cockpit-coverage       per-dataset / service health rows
  - aws-cockpit-assets         EC2 / S3 inventory from live metrics
  - aws-cockpit-events         AWS Health + CloudTrail + insight highlights
  - aws-cockpit-recommendations  (optional refresh via generate_aws_recommendations)

Usage:
  python3 seed_aws_insight_indices.py \\
    --obs-es https://....es....elastic.cloud \\
    --sec-es https://....es....elastic.cloud \\
    --obs-password "$OBS_PASSWORD" --sec-password "$SEC_PASSWORD"
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from base64 import b64encode
from datetime import datetime, timezone
from typing import Any
from urllib import error, request

try:
    from insight_fabric_common import (
        cloudtrail_failure_discover_href,
        recommendation_discover_href,
    )
except ImportError:
    # Allow running as a standalone script from any CWD.
    import pathlib
    import sys as _sys

    _sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from insight_fabric_common import (  # type: ignore
        cloudtrail_failure_discover_href,
        recommendation_discover_href,
    )

SECURITY_KPI = "aws-cockpit-security-kpi"
AWS_COCKPIT_DASHBOARD_ID = "752a1ac0-26e4-49d8-a2b4-5483068809b9"
COVERAGE = "aws-cockpit-coverage"
ASSETS = "aws-cockpit-assets"
EVENTS = "aws-cockpit-events"
HEALTH = "aws-cockpit-health"

# Canonical service tiles for the Datadog-style coverage matrix.
# `link` drills into the OOTB integration dashboard (or Fleet when not configured).
def _dash(did: str) -> str:
    return f"/app/dashboards#/view/{did}"


SERVICE_CATALOG = [
    {"service": "ec2", "label": "EC2", "datasets": ["aws.ec2_metrics"], "category": "compute", "link": _dash("aws-c5846400-f7fb-11e8-af03-c999c9dea608")},
    {"service": "s3", "label": "S3", "datasets": ["aws.s3_daily_storage", "aws.s3_request"], "category": "storage", "link": _dash("aws-a096b830-4762-11e9-8062-c98a86cb6f94")},
    {"service": "billing", "label": "Billing", "datasets": ["aws.billing"], "category": "cost", "link": _dash("aws-e6776b10-1534-11ea-841c-01bf20a6c8ba")},
    {"service": "vpcflow", "label": "VPC Flow", "datasets": ["aws.vpcflow"], "category": "network", "link": _dash("aws-15503340-4488-11ea-ad63-791a5dc86f10")},
    {"service": "cloudwatch", "label": "CloudWatch", "datasets": ["aws.cloudwatch_metrics"], "category": "platform", "link": _dash("aws-fac28650-7349-11e9-816b-07687310a99a")},
    {"service": "health", "label": "AWS Health", "datasets": ["aws.awshealth"], "category": "platform", "link": _dash("aws-9574244b-b538-4cc1-9666-8aac4ecf433e")},
    {"service": "cloudtrail", "label": "CloudTrail", "datasets": ["aws.cloudtrail"], "category": "security", "link": _dash("aws-9c09cd20-7399-11ea-a345-f985c61fe654")},
    {"service": "guardduty", "label": "GuardDuty", "datasets": ["aws.guardduty"], "category": "security", "link": _dash("aws-9d21f520-6a36-11ed-b880-2f1b70138655")},
    {"service": "securityhub", "label": "Security Hub", "datasets": ["aws.securityhub_findings", "aws.securityhub_insights"], "category": "security", "link": _dash("aws-c9f103d0-5f63-11ed-bd69-473ce047ef30")},
    {"service": "lambda", "label": "Lambda", "datasets": ["aws.lambda"], "category": "compute", "link": _dash("aws-7ac8e1d0-28d2-11ea-ba6c-49a884eb104f")},
    {"service": "rds", "label": "RDS", "datasets": ["aws.rds"], "category": "data", "link": _dash("aws-3367c170-921f-11e9-aa19-159bf182e06f")},
    {"service": "elb", "label": "ELB/ALB", "datasets": ["aws.elb_metrics", "aws.applicationelb"], "category": "network", "link": _dash("aws-24f3e07a-b5f5-470c-8305-47c9626db37b")},
]


def req(method: str, url: str, user: str, password: str, body: dict | None = None) -> Any:
    data = None if body is None else json.dumps(body).encode()
    headers = {
        "Authorization": "Basic " + b64encode(f"{user}:{password}".encode()).decode(),
        "Content-Type": "application/json",
    }
    request_obj = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(request_obj, timeout=120) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except error.HTTPError as e:
        err = e.read().decode()
        raise RuntimeError(f"{method} {url} -> {e.code}: {err[:500]}") from e


def esql(es: str, user: str, password: str, query: str) -> list[dict]:
    try:
        result = req("POST", f"{es}/_query", user, password, {"query": query})
    except RuntimeError as e:
        print(f"  esql warn: {e}", file=sys.stderr)
        return []
    cols = [c["name"] for c in result.get("columns", [])]
    rows = []
    for values in result.get("values", []) or []:
        rows.append({cols[i]: values[i] for i in range(len(cols))})
    return rows


def ensure_index(es: str, user: str, password: str, index: str, properties: dict) -> None:
    body = {"mappings": {"properties": properties}}
    try:
        req("PUT", f"{es}/{index}", user, password, body)
    except RuntimeError as e:
        if "resource_already_exists_exception" not in str(e):
            raise


def bulk_index(es: str, user: str, password: str, index: str, docs: list[tuple[str, dict]]) -> int:
    if not docs:
        return 0
    lines = []
    for doc_id, doc in docs:
        lines.append(json.dumps({"index": {"_index": index, "_id": doc_id}}))
        lines.append(json.dumps(doc))
    payload = ("\n".join(lines) + "\n").encode()
    headers = {
        "Authorization": "Basic " + b64encode(f"{user}:{password}".encode()).decode(),
        "Content-Type": "application/x-ndjson",
    }
    request_obj = request.Request(f"{es}/_bulk", data=payload, headers=headers, method="POST")
    with request.urlopen(request_obj, timeout=120) as resp:
        result = json.loads(resp.read().decode())
    if result.get("errors"):
        # Surface first error but still continue
        for item in result.get("items", []):
            err = (item.get("index") or {}).get("error")
            if err:
                print(f"  bulk error: {err}", file=sys.stderr)
                break
    return len(docs)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def scalar(rows: list[dict], key: str = "c", default: float | int = 0):
    if not rows:
        return default
    val = rows[0].get(key, default)
    return default if val is None else val


def seed_security_kpi(obs_es: str, sec_es: str, obs_user: str, obs_pass: str, sec_user: str, sec_pass: str) -> None:
    ensure_index(
        obs_es,
        obs_user,
        obs_pass,
        SECURITY_KPI,
        {
            "@timestamp": {"type": "date"},
            "kpi_id": {"type": "keyword"},
            "active_alerts": {"type": "long"},
            "high_critical_alerts": {"type": "long"},
            "cspm_findings": {"type": "long"},
            "guardduty_24h": {"type": "long"},
            "securityhub_24h": {"type": "long"},
            "cloudtrail_24h": {"type": "long"},
            "cloudtrail_failures_24h": {"type": "long"},
            "health_events": {"type": "long"},
        },
    )
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
    def count_or_zero(query: str) -> int:
        return int(scalar(esql(sec_es, sec_user, sec_pass, query)) or 0)

    # Empty datastreams throw on @timestamp filters — fall back to unfiltered count.
    guardduty = count_or_zero(
        "FROM logs-aws.guardduty* | WHERE @timestamp > NOW() - 24 hours | STATS c = COUNT(*)"
    ) or count_or_zero("FROM logs-aws.guardduty* | STATS c = COUNT(*)")
    securityhub = count_or_zero(
        "FROM logs-aws.securityhub* | WHERE @timestamp > NOW() - 24 hours | STATS c = COUNT(*)"
    ) or count_or_zero("FROM logs-aws.securityhub* | STATS c = COUNT(*)")
    cloudtrail = count_or_zero(
        "FROM logs-aws.cloudtrail* | WHERE @timestamp > NOW() - 24 hours | STATS c = COUNT(*)"
    ) or count_or_zero("FROM logs-aws.cloudtrail* | STATS c = COUNT(*)")
    cloudtrail_failures = count_or_zero(
        'FROM logs-aws.cloudtrail* | WHERE @timestamp > NOW() - 24 hours AND event.outcome == "failure" | STATS c = COUNT(*)'
    )
    health = count_or_zero(
        "FROM metrics-aws.awshealth-default | STATS c = COUNT_DISTINCT(aws.awshealth.event_arn)"
    ) or count_or_zero("FROM metrics-aws.awshealth* | STATS c = COUNT(*)")
    # Also try OBS-local CSPM aliases so the number isn't stuck at 0 if findings land there.
    cspm_obs = scalar(
        esql(
            obs_es,
            obs_user,
            obs_pass,
            "FROM security_solution-*.misconfiguration_latest | STATS c = COUNT(*)",
        )
    )
    cspm_total = max(int(cspm or 0), int(cspm_obs or 0))
    doc = {
        "@timestamp": now_iso(),
        "kpi_id": "current",
        "active_alerts": int(active or 0),
        "high_critical_alerts": int(high or 0),
        "cspm_findings": cspm_total,
        "guardduty_24h": int(guardduty or 0),
        "securityhub_24h": int(securityhub or 0),
        "cloudtrail_24h": int(cloudtrail or 0),
        "cloudtrail_failures_24h": int(cloudtrail_failures or 0),
        "health_events": int(health or 0),
    }
    bulk_index(obs_es, obs_user, obs_pass, SECURITY_KPI, [("current", doc)])
    print(f"  {SECURITY_KPI}: {doc}")


def seed_coverage(
    obs_es: str,
    sec_es: str,
    obs_user: str,
    obs_pass: str,
    sec_user: str,
    sec_pass: str,
    *,
    sec_kibana: str = "",
) -> None:
    ensure_index(
        obs_es,
        obs_user,
        obs_pass,
        COVERAGE,
        {
            "@timestamp": {"type": "date"},
            "service": {"type": "keyword"},
            "label": {"type": "keyword"},
            "category": {"type": "keyword"},
            "status": {"type": "keyword"},
            "docs_24h": {"type": "long"},
            "last_seen": {"type": "date"},
            "datasets": {"type": "keyword"},
            "detail": {"type": "keyword"},
            "link": {"type": "keyword"},
        },
    )
    # Merge OBS + SEC dataset stats (wildcard + explicit probes for sparse streams)
    dataset_stats: dict[str, dict] = {}

    def absorb(rows: list[dict]) -> None:
        for row in rows:
            ds = row.get("data_stream.dataset") or row.get("dataset")
            if not ds:
                continue
            prev = dataset_stats.get(ds)
            if not prev or (row.get("docs") or 0) >= (prev.get("docs") or 0):
                dataset_stats[ds] = {
                    "data_stream.dataset": ds,
                    "docs": row.get("docs") or 0,
                    "last_seen": row.get("last_seen"),
                }

    for es, user, pw in (
        (obs_es, obs_user, obs_pass),
        (sec_es, sec_user, sec_pass),
    ):
        absorb(
            esql(
                es,
                user,
                pw,
                """FROM logs-*, metrics-*
| WHERE @timestamp > NOW() - 7 days
| STATS docs = COUNT(*), last_seen = MAX(@timestamp) BY data_stream.dataset
| SORT docs DESC
| LIMIT 200""",
            )
        )
    # Explicit probes — some streams are missed by logs-*,metrics-* wildcards
    for es, user, pw, probes in (
        (
            obs_es,
            obs_user,
            obs_pass,
            ["metrics-aws.ec2_metrics*", "metrics-aws.s3*", "metrics-aws.billing*", "logs-aws.vpcflow*"],
        ),
        (
            sec_es,
            sec_user,
            sec_pass,
            [
                "metrics-aws.awshealth*",
                "logs-aws.cloudtrail*",
                "logs-aws.guardduty*",
                "logs-aws.securityhub*",
            ],
        ),
    ):
        for pattern in probes:
            rows = esql(
                es,
                user,
                pw,
                f"""FROM {pattern}
| STATS docs = COUNT(*), last_seen = MAX(@timestamp), dataset = VALUES(data_stream.dataset)
| LIMIT 1""",
            )
            for row in rows:
                ds = row.get("dataset")
                if isinstance(ds, list):
                    ds = ds[0] if ds else None
                if not ds:
                    # infer from pattern
                    ds = (
                        pattern.replace("metrics-", "")
                        .replace("logs-", "")
                        .replace("*", "")
                        .rstrip("-default")
                        .replace("_metrics", "_metrics")
                    )
                    # normalize common ones
                    mapping = {
                        "aws.ec2_metrics": "aws.ec2_metrics",
                        "aws.s3": "aws.s3_daily_storage",
                        "aws.billing": "aws.billing",
                        "aws.vpcflow": "aws.vpcflow",
                        "aws.awshealth": "aws.awshealth",
                        "aws.cloudtrail": "aws.cloudtrail",
                        "aws.guardduty": "aws.guardduty",
                        "aws.securityhub": "aws.securityhub_findings",
                    }
                    for key, val in mapping.items():
                        if key in pattern or key in (ds or ""):
                            ds = val
                            break
                if ds and (row.get("docs") or 0) > 0:
                    absorb(
                        [
                            {
                                "data_stream.dataset": ds,
                                "docs": row.get("docs") or 0,
                                "last_seen": row.get("last_seen"),
                            }
                        ]
                    )

    docs = []
    ts = now_iso()
    for svc in SERVICE_CATALOG:
        matched = [dataset_stats[d] for d in svc["datasets"] if d in dataset_stats]
        docs_24h = int(sum((m.get("docs") or 0) for m in matched))
        last_seen = None
        for m in matched:
            ls = m.get("last_seen")
            if ls and (last_seen is None or str(ls) > str(last_seen)):
                last_seen = ls
        # Services we intentionally do not collect yet — show as not_configured
        # (Datadog-style tile) rather than a red "missing" failure.
        optional_services = {"lambda", "rds", "elb", "guardduty", "securityhub"}
        if docs_24h > 0:
            status = "healthy"
            detail = f"{docs_24h} docs"
        elif svc["service"] in optional_services:
            status = "not_configured"
            detail = "integration not enabled"
        else:
            status = "missing"
            detail = "no data yet"
        # Freshness windows match collection cadence (billing/health = 12–24h).
        stale_after_h = {
            "billing": 36,
            "health": 36,
            "s3": 36,
            "vpcflow": 24,
            "cloudtrail": 12,
        }.get(svc["service"], 8)
        if last_seen and status == "healthy":
            try:
                # Elastic returns epoch ms or iso
                if isinstance(last_seen, (int, float)):
                    age_h = (time.time() * 1000 - float(last_seen)) / 3600000
                else:
                    age_h = (
                        datetime.now(timezone.utc)
                        - datetime.fromisoformat(str(last_seen).replace("Z", "+00:00"))
                    ).total_seconds() / 3600
                if age_h > stale_after_h:
                    status = "stale"
                    detail = f"last seen {age_h:.1f}h ago"
            except Exception:
                pass
        link = svc.get("link") or (
            "/app/fleet/integrations" if status == "not_configured" else "/app/discover"
        )
        # Security-project OOTB boards need an absolute Security Kibana base.
        sec_services = {"cloudtrail", "guardduty", "securityhub", "health"}
        if sec_kibana and svc["service"] in sec_services and link.startswith("/"):
            link = sec_kibana.rstrip("/") + link
        docs.append(
            (
                svc["service"],
                {
                    "@timestamp": ts,
                    "service": svc["service"],
                    "label": svc["label"],
                    "category": svc["category"],
                    "status": status,
                    "docs_24h": docs_24h,
                    "last_seen": last_seen,
                    "datasets": svc["datasets"],
                    "detail": detail,
                    "link": link,
                },
            )
        )
    bulk_index(obs_es, obs_user, obs_pass, COVERAGE, docs)
    healthy = sum(1 for _, d in docs if d["status"] == "healthy")
    print(f"  {COVERAGE}: {healthy}/{len(docs)} healthy services")


def seed_assets(obs_es: str, obs_user: str, obs_pass: str) -> None:
    ensure_index(
        obs_es,
        obs_user,
        obs_pass,
        ASSETS,
        {
            "@timestamp": {"type": "date"},
            "resource": {
                "properties": {
                    "type": {"type": "keyword"},
                    "name": {"type": "keyword"},
                    "id": {"type": "keyword"},
                }
            },
            "cloud": {
                "properties": {
                    "region": {"type": "keyword"},
                    "availability_zone": {"type": "keyword"},
                    "account": {"properties": {"id": {"type": "keyword"}}},
                    "machine": {"properties": {"type": {"type": "keyword"}}},
                }
            },
            "metric_name": {"type": "keyword"},
            "metric_value": {"type": "double"},
            "last_seen": {"type": "date"},
        },
    )
    ts = now_iso()
    docs: list[tuple[str, dict]] = []
    ec2 = esql(
        obs_es,
        obs_user,
        obs_pass,
        """FROM metrics-aws.ec2_metrics-default
| WHERE @timestamp > NOW() - 24 hours
| STATS avg_cpu = AVG(aws.ec2.metrics.CPUUtilization.avg), last_seen = MAX(@timestamp)
    BY cloud.instance.id, cloud.instance.name, cloud.region, cloud.availability_zone, cloud.account.id, cloud.machine.type
| SORT avg_cpu ASC
| LIMIT 200""",
    )
    for row in ec2:
        rid = row.get("cloud.instance.id") or row.get("cloud.instance.name") or "unknown"
        name = row.get("cloud.instance.name") or rid
        docs.append(
            (
                f"ec2-{rid}",
                {
                    "@timestamp": ts,
                    "resource": {"type": "ec2_instance", "name": name, "id": rid},
                    "cloud": {
                        "region": row.get("cloud.region"),
                        "availability_zone": row.get("cloud.availability_zone"),
                        "account": {"id": row.get("cloud.account.id")},
                        "machine": {"type": row.get("cloud.machine.type")},
                    },
                    "metric_name": "cpu_avg_24h",
                    "metric_value": row.get("avg_cpu") or 0,
                    "last_seen": row.get("last_seen"),
                },
            )
        )
    s3 = esql(
        obs_es,
        obs_user,
        obs_pass,
        """FROM metrics-aws.s3_daily_storage-default
| WHERE @timestamp > NOW() - 7 days
| STATS max_size = MAX(aws.s3_daily_storage.bucket.size.bytes), last_seen = MAX(@timestamp)
    BY aws.s3.bucket.name, cloud.region, cloud.account.id
| SORT max_size DESC
| LIMIT 300""",
    )
    for row in s3:
        name = row.get("aws.s3.bucket.name") or "unknown"
        docs.append(
            (
                f"s3-{name}",
                {
                    "@timestamp": ts,
                    "resource": {"type": "s3_bucket", "name": name, "id": name},
                    "cloud": {
                        "region": row.get("cloud.region"),
                        "account": {"id": row.get("cloud.account.id")},
                    },
                    "metric_name": "bucket_size_bytes",
                    "metric_value": row.get("max_size") or 0,
                    "last_seen": row.get("last_seen"),
                },
            )
        )
    bulk_index(obs_es, obs_user, obs_pass, ASSETS, docs)
    print(f"  {ASSETS}: {len(docs)} resources")


def seed_health(obs_es: str, sec_es: str, obs_user: str, obs_pass: str, sec_user: str, sec_pass: str) -> None:
    """Mirror AWS Health metrics into Observability so Health panels never hit CPS."""
    ensure_index(
        obs_es,
        obs_user,
        obs_pass,
        HEALTH,
        {
            "@timestamp": {"type": "date"},
            "aws.awshealth.event_arn": {"type": "keyword"},
            "aws.awshealth.service": {"type": "keyword"},
            "aws.awshealth.region": {"type": "keyword"},
            "aws.awshealth.event_type_category": {"type": "keyword"},
            "aws.awshealth.event_type_code": {"type": "keyword"},
            "aws.awshealth.status_code": {"type": "keyword"},
            "aws.awshealth.event_description": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 1024}},
            },
            "aws.awshealth.last_updated_time": {"type": "date"},
            "aws.awshealth.affected_entities_pending": {"type": "long"},
        },
    )
    rows = esql(
        sec_es,
        sec_user,
        sec_pass,
        """FROM metrics-aws.awshealth-default
| STATS last_seen = MAX(@timestamp),
        last_updated = MAX(aws.awshealth.last_updated_time),
        open_entities = MAX(aws.awshealth.affected_entities_pending),
        category = VALUES(aws.awshealth.event_type_category),
        status = VALUES(aws.awshealth.status_code),
        region = VALUES(aws.awshealth.region),
        description = VALUES(aws.awshealth.event_description)
    BY aws.awshealth.event_arn, aws.awshealth.service, aws.awshealth.event_type_code
| SORT last_seen DESC
| LIMIT 200""",
    )
    docs: list[tuple[str, dict]] = []
    ts = now_iso()
    for i, row in enumerate(rows):
        arn = row.get("aws.awshealth.event_arn") or f"health-{i}"

        def first(v):
            if isinstance(v, list):
                return v[0] if v else None
            return v

        status = first(row.get("status"))
        category = first(row.get("category"))
        region = first(row.get("region"))
        description = first(row.get("description"))
        docs.append(
            (
                f"health-{abs(hash(arn)) % 10_000_000}",
                {
                    "@timestamp": row.get("last_seen") or ts,
                    "aws.awshealth.event_arn": arn,
                    "aws.awshealth.service": row.get("aws.awshealth.service"),
                    "aws.awshealth.region": region,
                    "aws.awshealth.event_type_category": category,
                    "aws.awshealth.event_type_code": row.get("aws.awshealth.event_type_code"),
                    "aws.awshealth.status_code": status,
                    "aws.awshealth.event_description": description,
                    "aws.awshealth.last_updated_time": row.get("last_updated") or row.get("last_seen") or ts,
                    "aws.awshealth.affected_entities_pending": int(row.get("open_entities") or 0),
                },
            )
        )
    bulk_index(obs_es, obs_user, obs_pass, HEALTH, docs)
    print(f"  {HEALTH}: {len(docs)} events")


def seed_events(
    obs_es: str,
    sec_es: str,
    obs_user: str,
    obs_pass: str,
    sec_user: str,
    sec_pass: str,
    *,
    sec_kibana: str = "",
) -> None:
    ensure_index(
        obs_es,
        obs_user,
        obs_pass,
        EVENTS,
        {
            "@timestamp": {"type": "date"},
            "event.source": {"type": "keyword"},
            "event.severity": {"type": "keyword"},
            "event.category": {"type": "keyword"},
            "title": {"type": "keyword"},
            "detail": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 512}},
            },
            "service": {"type": "keyword"},
            "cloud.region": {"type": "keyword"},
            "link": {"type": "keyword"},
        },
    )
    # Drop prior snapshot so volume-style CloudTrail rows don't linger beside failures.
    try:
        req(
            "POST",
            f"{obs_es}/{EVENTS}/_delete_by_query?refresh=true",
            obs_user,
            obs_pass,
            {"query": {"match_all": {}}},
        )
    except RuntimeError as e:
        print(f"  events purge warn: {e}", file=sys.stderr)
    docs: list[tuple[str, dict]] = []
    ts = now_iso()
    # CloudTrail / Health OOTB boards live in the Security project — use absolute URLs.
    sec_kb = (sec_kibana or "").rstrip("/")
    cloudtrail_dash = (
        f"{sec_kb}/app/dashboards#/view/aws-9c09cd20-7399-11ea-a345-f985c61fe654"
        if sec_kb
        else "/app/dashboards#/view/aws-9c09cd20-7399-11ea-a345-f985c61fe654"
    )
    health_dash = (
        f"{sec_kb}/app/dashboards#/view/aws-9574244b-b538-4cc1-9666-8aac4ecf433e"
        if sec_kb
        else "/app/dashboards#/view/aws-9574244b-b538-4cc1-9666-8aac4ecf433e"
    )
    # Recommendations section on this Obs cockpit (dashboard deep-link for overview).
    recs_dash = f"/app/dashboards#/view/{AWS_COCKPIT_DASHBOARD_ID}"

    # Recommendations first — these are the actionable "problems"
    recs = esql(
        obs_es,
        obs_user,
        obs_pass,
        """FROM aws-cockpit-recommendations
| WHERE @timestamp > NOW() - 7 days
| STATS c = COUNT(*) BY severity, category
| SORT c DESC
| LIMIT 10""",
    )
    for row in recs:
        sev = row.get("severity") or "low"
        cat = row.get("category") or "insight"
        count = int(row.get("c") or 0)
        label = str(cat).replace("_", " ")
        # Category/severity → Discover detail table; cost_optimization etc. open filtered rows.
        detail_link = recommendation_discover_href(
            "aws-cockpit-recommendations", category=str(cat), severity=str(sev)
        )
        docs.append(
            (
                f"rec-{sev}-{cat}",
                {
                    "@timestamp": ts,
                    "event.source": "cockpit.recommendations",
                    "event.severity": sev,
                    "event.category": cat,
                    "title": f"{count} {label} recommendations",
                    "detail": (
                        f"{sev} {label} — open filtered recommendation details "
                        f"(or cockpit recommendations section) →"
                    ),
                    "service": "recommendations",
                    "link": detail_link or recs_dash,
                },
            )
        )

    # CloudTrail failures — show the actual problem (failed API actions), not volume
    ct_fail = esql(
        sec_es,
        sec_user,
        sec_pass,
        """FROM logs-aws.cloudtrail*
| WHERE @timestamp > NOW() - 24 hours AND event.outcome == "failure"
| STATS c = COUNT(*) BY event.action, event.provider
| SORT c DESC
| LIMIT 8""",
    )
    for row in ct_fail:
        action = row.get("event.action") or "UnknownAction"
        provider = row.get("event.provider") or "cloudtrail"
        count = int(row.get("c") or 0)
        short = str(provider).replace(".amazonaws.com", "")
        # Prefer action-filtered Discover in Security; fall back to OOTB CloudTrail board.
        fail_link = cloudtrail_failure_discover_href(str(action), kibana_base=sec_kb)
        docs.append(
            (
                f"cloudtrail-fail-{action}",
                {
                    "@timestamp": ts,
                    "event.source": "aws.cloudtrail",
                    "event.severity": "high" if count >= 10000 else "medium",
                    "event.category": "api_failure",
                    "title": f"{count:,} failed {action}",
                    "detail": (
                        f"CloudTrail API failures from {short} (24h) — "
                        f"open failed {action} events →"
                    ),
                    "service": short,
                    "link": fail_link or cloudtrail_dash,
                },
            )
        )

    # Open / upcoming AWS Health only (skip noise from closed events)
    health = esql(
        sec_es,
        sec_user,
        sec_pass,
        """FROM metrics-aws.awshealth-default
| STATS last_seen = MAX(@timestamp),
        open_entities = MAX(aws.awshealth.affected_entities_pending),
        category = VALUES(aws.awshealth.event_type_category),
        status = VALUES(aws.awshealth.status_code),
        region = VALUES(aws.awshealth.region)
    BY aws.awshealth.event_arn, aws.awshealth.service, aws.awshealth.event_type_code
| SORT last_seen DESC
| LIMIT 40""",
    )
    health_kept = 0
    for i, row in enumerate(health):
        status = row.get("status")
        if isinstance(status, list):
            status = status[0] if status else "unknown"
        if status not in ("open", "upcoming"):
            continue
        arn = row.get("aws.awshealth.event_arn") or f"health-{i}"
        service = row.get("aws.awshealth.service") or "AWS"
        code = row.get("aws.awshealth.event_type_code") or "event"
        category = row.get("category")
        if isinstance(category, list):
            category = category[0] if category else "issue"
        region = row.get("region")
        if isinstance(region, list):
            region = region[0] if region else None
        docs.append(
            (
                f"health-{abs(hash(arn)) % 10_000_000}",
                {
                    "@timestamp": row.get("last_seen") or ts,
                    "event.source": "aws.health",
                    "event.severity": "high",
                    "event.category": str(category),
                    "title": f"{service}: {code}",
                    "detail": f"AWS Health {status} — open Health dashboard →",
                    "service": service,
                    "cloud.region": region,
                    "link": health_dash,
                },
            )
        )
        health_kept += 1
        if health_kept >= 6:
            break

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
        "--sec-kibana",
        default="",
        help="Security Kibana base URL for absolute CloudTrail/Health drill-downs",
    )
    args = p.parse_args()
    obs_es = args.obs_es.rstrip("/")
    sec_es = args.sec_es.rstrip("/")

    print("Seeding AWS cockpit insight indices…")
    seed_security_kpi(obs_es, sec_es, args.obs_user, args.obs_password, args.sec_user, args.sec_password)
    seed_coverage(
        obs_es,
        sec_es,
        args.obs_user,
        args.obs_password,
        args.sec_user,
        args.sec_password,
        sec_kibana=args.sec_kibana,
    )
    seed_assets(obs_es, args.obs_user, args.obs_password)
    seed_health(obs_es, sec_es, args.obs_user, args.obs_password, args.sec_user, args.sec_password)
    seed_events(
        obs_es,
        sec_es,
        args.obs_user,
        args.obs_password,
        args.sec_user,
        args.sec_password,
        sec_kibana=args.sec_kibana,
    )
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
