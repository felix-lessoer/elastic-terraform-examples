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

SECURITY_KPI = "aws-cockpit-security-kpi"
COVERAGE = "aws-cockpit-coverage"
ASSETS = "aws-cockpit-assets"
EVENTS = "aws-cockpit-events"
HEALTH = "aws-cockpit-health"

# Canonical service tiles for the Datadog-style coverage matrix.
SERVICE_CATALOG = [
    {"service": "ec2", "label": "EC2", "datasets": ["aws.ec2_metrics"], "category": "compute"},
    {"service": "s3", "label": "S3", "datasets": ["aws.s3_daily_storage", "aws.s3_request"], "category": "storage"},
    {"service": "billing", "label": "Billing", "datasets": ["aws.billing"], "category": "cost"},
    {"service": "vpcflow", "label": "VPC Flow", "datasets": ["aws.vpcflow"], "category": "network"},
    {"service": "cloudwatch", "label": "CloudWatch", "datasets": ["aws.cloudwatch_metrics"], "category": "platform"},
    {"service": "health", "label": "AWS Health", "datasets": ["aws.awshealth"], "category": "platform"},
    {"service": "cloudtrail", "label": "CloudTrail", "datasets": ["aws.cloudtrail"], "category": "security"},
    {"service": "guardduty", "label": "GuardDuty", "datasets": ["aws.guardduty"], "category": "security"},
    {"service": "securityhub", "label": "Security Hub", "datasets": ["aws.securityhub_findings", "aws.securityhub_insights"], "category": "security"},
    {"service": "lambda", "label": "Lambda", "datasets": ["aws.lambda"], "category": "compute"},
    {"service": "rds", "label": "RDS", "datasets": ["aws.rds"], "category": "data"},
    {"service": "elb", "label": "ELB/ALB", "datasets": ["aws.elb_metrics", "aws.applicationelb"], "category": "network"},
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
        "health_events": int(health or 0),
    }
    bulk_index(obs_es, obs_user, obs_pass, SECURITY_KPI, [("current", doc)])
    print(f"  {SECURITY_KPI}: {doc}")


def seed_coverage(obs_es: str, sec_es: str, obs_user: str, obs_pass: str, sec_user: str, sec_pass: str) -> None:
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


def seed_events(obs_es: str, sec_es: str, obs_user: str, obs_pass: str, sec_user: str, sec_pass: str) -> None:
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
    docs: list[tuple[str, dict]] = []
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
| LIMIT 25""",
    )
    for i, row in enumerate(health):
        arn = row.get("aws.awshealth.event_arn") or f"health-{i}"
        service = row.get("aws.awshealth.service") or "AWS"
        code = row.get("aws.awshealth.event_type_code") or "event"
        status = row.get("status")
        if isinstance(status, list):
            status = status[0] if status else "unknown"
        category = row.get("category")
        if isinstance(category, list):
            category = category[0] if category else "issue"
        severity = "high" if status in ("open", "upcoming") else "medium"
        region = row.get("region")
        if isinstance(region, list):
            region = region[0] if region else None
        docs.append(
            (
                f"health-{abs(hash(arn)) % 10_000_000}",
                {
                    "@timestamp": row.get("last_seen") or now_iso(),
                    "event.source": "aws.health",
                    "event.severity": severity,
                    "event.category": str(category),
                    "title": f"{service}: {code}",
                    "detail": f"AWS Health {status} — {service} / {code}",
                    "service": service,
                    "cloud.region": region,
                    "link": "/app/dashboards#/view/aws-9574244b-b538-4cc1-9666-8aac4ecf433e",
                },
            )
        )

    # CloudTrail volume spike / daily highlight (not every event — summary insight)
    ct = esql(
        sec_es,
        sec_user,
        sec_pass,
        """FROM logs-aws.cloudtrail*
| WHERE @timestamp > NOW() - 24 hours
| STATS c = COUNT(*) BY event.provider
| SORT c DESC
| LIMIT 8""",
    )
    ts = now_iso()
    for row in ct:
        provider = row.get("event.provider") or "cloudtrail"
        count = int(row.get("c") or 0)
        docs.append(
            (
                f"cloudtrail-{provider}",
                {
                    "@timestamp": ts,
                    "event.source": "aws.cloudtrail",
                    "event.severity": "info",
                    "event.category": "api_activity",
                    "title": f"CloudTrail: {provider}",
                    "detail": f"{count:,} management events in the last 24h",
                    "service": str(provider).replace(".amazonaws.com", ""),
                    "link": "/app/dashboards#/view/aws-9c09cd20-7399-11ea-a345-f985c61fe654",
                },
            )
        )

    # Recommendation highlights from OBS
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
        docs.append(
            (
                f"rec-{sev}-{cat}",
                {
                    "@timestamp": ts,
                    "event.source": "cockpit.recommendations",
                    "event.severity": sev,
                    "event.category": cat,
                    "title": f"{int(row.get('c') or 0)} {sev} {cat} recommendations",
                    "detail": "From scheduled EC2/S3 recommendation workflows",
                    "service": "recommendations",
                    "link": "#aws-recommendations",
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

    print("Seeding AWS cockpit insight indices…")
    seed_security_kpi(obs_es, sec_es, args.obs_user, args.obs_password, args.sec_user, args.sec_password)
    seed_coverage(obs_es, sec_es, args.obs_user, args.obs_password, args.sec_user, args.sec_password)
    seed_assets(obs_es, args.obs_user, args.obs_password)
    seed_health(obs_es, sec_es, args.obs_user, args.obs_password, args.sec_user, args.sec_password)
    seed_events(obs_es, sec_es, args.obs_user, args.obs_password, args.sec_user, args.sec_password)
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
