#!/usr/bin/env python3
"""Build a deterministic GCP recommendation snapshot from observed metrics."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from base64 import b64encode
from datetime import datetime, timezone


INDEX = "gcp-cockpit-recommendations"
CPU_LOW = 5.0
CPU_HIGH = 85.0


def resource_key(project: object, region: object, kind: str, rid: object) -> str:
    return f"{project or 'unknown'}:{region or 'global'}:{kind}:{rid}"


def req(method: str, url: str, user: str, password: str, body: dict | None = None):
    request = urllib.request.Request(
        url,
        data=None if body is None else json.dumps(body).encode(),
        headers={
            "Authorization": "Basic "
            + b64encode(f"{user}:{password}".encode()).decode(),
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = response.read()
            return json.loads(payload) if payload else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode()
        raise RuntimeError(
            f"{method} {url} -> {error.code}: {detail[:500]}"
        ) from error


def esql(es: str, user: str, password: str, query: str) -> list[dict]:
    try:
        result = req("POST", f"{es}/_query", user, password, {"query": query})
    except RuntimeError as exc:
        if "Unknown index" not in str(exc) and "Unknown column" not in str(exc):
            raise
        print(f"  esql warn: {exc}", file=sys.stderr)
        return []
    columns = [column["name"] for column in result.get("columns", [])]
    return [
        {columns[index]: value for index, value in enumerate(values)}
        for values in result.get("values", [])
    ]


def ensure_index(es: str, user: str, password: str) -> None:
    properties = {
        "@timestamp": {"type": "date"},
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
                "region": {"type": "keyword"},
                "project": {"properties": {"id": {"type": "keyword"}}},
            }
        },
    }
    try:
        req(
            "PUT",
            f"{es}/{INDEX}",
            user,
            password,
            {"settings": {"index.mode": "lookup"}, "mappings": {"properties": properties}},
        )
    except RuntimeError as exc:
        if "resource_already_exists_exception" not in str(exc):
            raise
    req("PUT", f"{es}/{INDEX}/_mapping", user, password, {"properties": properties})


def finding(
    *,
    now: str,
    project: object,
    region: object,
    kind: str,
    rid: object,
    name: object,
    category: str,
    severity: str,
    metric_name: str,
    metric_value: float,
    threshold: float,
    recommendation: str,
    lookback_days: int,
    confidence: str = "high",
    activity_status: str = "observed",
    missing_telemetry: list[str] | None = None,
) -> tuple[str, dict]:
    stable_key = resource_key(project, region, kind, rid)
    return (
        f"{stable_key}:{category}:{metric_name}",
        {
            "@timestamp": now,
            "category": category,
            "severity": severity,
            "confidence": confidence,
            "activity_status": activity_status,
            "lookback_days": lookback_days,
            "evidence_refs": [metric_name],
            "contradictory_evidence": [],
            "missing_telemetry": missing_telemetry or [],
            "expected_value": f"{metric_name} within threshold {threshold}",
            "safe_next_action": recommendation,
            "metric_name": metric_name,
            "metric_value": metric_value,
            "threshold": threshold,
            "recommendation": recommendation,
            "resource": {
                "key": stable_key,
                "type": kind,
                "name": name,
                "id": rid,
            },
            "cloud": {"region": region, "project": {"id": project}},
        },
    )


def build_recommendations(
    compute: list[dict], storage: list[dict], now: str
) -> list[tuple[str, dict]]:
    documents: list[tuple[str, dict]] = []
    for row in compute:
        rid = row.get("instance_id") or row.get("instance") or "unknown"
        name = row.get("instance") or rid
        common = {
            "now": now,
            "project": row.get("project"),
            "region": row.get("region"),
            "kind": "gce_instance",
            "rid": rid,
            "name": name,
            "lookback_days": 14,
        }
        avg_cpu = float(row.get("avg_cpu") or 0)
        if avg_cpu > CPU_HIGH:
            message = f"GCE instance {name} averaged {avg_cpu:.2f}% CPU; review capacity."
            documents.append(
                finding(
                    **common,
                    category="performance_risk",
                    severity="high",
                    metric_name="avg_cpu_pct",
                    metric_value=avg_cpu,
                    threshold=CPU_HIGH,
                    recommendation=message,
                )
            )
        network_in, network_out = row.get("network_in"), row.get("network_out")
        # An absent stream is not zero activity. Both activity metrics and at
        # least one source document must have been observed before this finding.
        if (
            int(row.get("observations") or 0) > 0
            and network_in is not None
            and network_out is not None
            and avg_cpu < 1
            and float(network_in) + float(network_out) < 10_485_760
        ):
            traffic = float(network_in) + float(network_out)
            message = (
                f"GCE instance {name} had low CPU and {traffic:.0f} observed "
                "network bytes over 14 days; confirm ownership before stopping it."
            )
            documents.append(
                finding(
                    **common,
                    category="unused_resource",
                    severity="medium",
                    metric_name="network_bytes_14d",
                    metric_value=traffic,
                    threshold=10_485_760,
                    recommendation=message,
                    activity_status="potentially_unused",
                )
            )

    for row in storage:
        size, requests = row.get("size"), row.get("requests")
        if (
            int(row.get("observations") or 0) <= 0
            or size is None
            or requests is None
            or float(size) > 0
            or float(requests) > 0
        ):
            continue
        name = row.get("bucket") or "unknown"
        message = (
            f"GCS bucket {name} had observed zero bytes and zero requests over "
            "7 days; confirm retention and owner requirements before removal."
        )
        documents.append(
            finding(
                now=now,
                project=row.get("project"),
                region=row.get("region"),
                kind="gcs_bucket",
                rid=name,
                name=name,
                category="unused_resource",
                severity="low",
                metric_name="request_count_7d",
                metric_value=0,
                threshold=0,
                recommendation=message,
                lookback_days=7,
                activity_status="potentially_unused",
            )
        )
    return documents


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--es-url", required=True)
    parser.add_argument("--user", default="admin")
    parser.add_argument("--password", required=True)
    args = parser.parse_args()
    es = args.es_url.rstrip("/")
    ensure_index(es, args.user, args.password)
    compute = esql(
        es,
        args.user,
        args.password,
        """FROM metrics-gcp.compute-default
| WHERE @timestamp > NOW() - 14 days
| EVAL cpu_pct = gcp.compute.instance.cpu.usage.pct * 100
| STATS observations = COUNT(*),
        avg_cpu = AVG(cpu_pct),
        network_in = SUM(gcp.compute.instance.network.received.bytes),
        network_out = SUM(gcp.compute.instance.network.sent.bytes)
  BY instance = cloud.instance.name, instance_id = cloud.instance.id,
     region = cloud.region, project = cloud.account.id
| WHERE instance_id IS NOT NULL
| LIMIT 200""",
    )
    storage = esql(
        es,
        args.user,
        args.password,
        """FROM metrics-gcp.storage-default
| WHERE @timestamp > NOW() - 7 days
| STATS observations = COUNT(*),
        size = MAX(gcp.storage.storage.total.bytes),
        requests = SUM(gcp.storage.api.request.count)
  BY bucket = gcp.labels.resource.bucket_name,
     region = gcp.labels.resource.location, project = cloud.account.id
| WHERE bucket IS NOT NULL
| LIMIT 200""",
    )
    now = datetime.now(timezone.utc).isoformat()
    documents = build_recommendations(compute, storage, now)
    try:
        req(
            "POST",
            f"{es}/{INDEX}/_delete_by_query?conflicts=proceed&refresh=true",
            args.user,
            args.password,
            {"query": {"match_all": {}}},
        )
    except RuntimeError as exc:
        print(f"Recommendation snapshot cleanup warning: {exc}", file=sys.stderr)
    if documents:
        lines = []
        for doc_id, document in documents:
            lines.extend(
                [
                    json.dumps({"index": {"_index": INDEX, "_id": doc_id}}),
                    json.dumps(document),
                ]
            )
        request = urllib.request.Request(
            f"{es}/_bulk",
            data=("\n".join(lines) + "\n").encode(),
            headers={
                "Authorization": "Basic "
                + b64encode(f"{args.user}:{args.password}".encode()).decode(),
                "Content-Type": "application/x-ndjson",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.loads(response.read())
        if result.get("errors"):
            return 1
    req("POST", f"{es}/{INDEX}/_refresh", args.user, args.password)
    print(f"Indexed {len(documents)} deterministic recommendations into {INDEX}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
