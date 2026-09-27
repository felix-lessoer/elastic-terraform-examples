#!/usr/bin/env python3
"""Generate aws-cockpit-recommendations from live AWS metrics.

Mirrors the GCP concept behind `gcp-cockpit-recommendations`:
  - cost_optimization: underutilized EC2 (avg CPU < 5% / 24h), empty S3 buckets
  - performance_risk: hot EC2 (avg CPU > 85%), failed status checks

Usage:
  python3 generate_aws_recommendations.py \\
    --es-url https://aws-observability-cockpit-....es....elastic.cloud \\
    --user admin --password "$OBS_PASSWORD"
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from base64 import b64encode


INDEX = "aws-cockpit-recommendations"
CPU_LOW = 5.0
CPU_HIGH = 85.0


def req(method: str, url: str, user: str, password: str, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    headers = {
        "Authorization": "Basic " + b64encode(f"{user}:{password}".encode()).decode(),
        "Content-Type": "application/json",
    }
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=120) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        raise RuntimeError(f"{method} {url} -> {e.code}: {err[:500]}") from e


def esql(es: str, user: str, password: str, query: str) -> list[dict]:
    result = req("POST", f"{es}/_query", user, password, {"query": query})
    cols = [c["name"] for c in result.get("columns", [])]
    rows = []
    for values in result.get("values", []):
        rows.append({cols[i]: values[i] for i in range(len(cols))})
    return rows


def ensure_index(es: str, user: str, password: str) -> None:
    mapping = {
        "mappings": {
            "properties": {
                "@timestamp": {"type": "date"},
                "category": {"type": "keyword"},
                "severity": {"type": "keyword"},
                "metric_name": {"type": "keyword"},
                "metric_value": {"type": "double"},
                "threshold": {"type": "double"},
                "recommendation": {
                    "type": "text",
                    "fields": {"keyword": {"type": "keyword", "ignore_above": 512}},
                },
                "resource": {
                    "properties": {
                        "name": {"type": "keyword"},
                        "type": {"type": "keyword"},
                    }
                },
                "cloud": {
                    "properties": {
                        "availability_zone": {"type": "keyword"},
                        "account": {"properties": {"id": {"type": "keyword"}}},
                        "region": {"type": "keyword"},
                    }
                },
            }
        }
    }
    # Create if missing; ignore resource_already_exists
    try:
        req("PUT", f"{es}/{INDEX}", user, password, mapping)
    except RuntimeError as e:
        if "resource_already_exists_exception" not in str(e):
            raise


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--es-url", required=True)
    p.add_argument("--user", default="admin")
    p.add_argument("--password", required=True)
    args = p.parse_args()
    es = args.es_url.rstrip("/")

    ensure_index(es, args.user, args.password)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M")
    docs: list[tuple[str, dict]] = []

    # EC2 CPU + status
    ec2 = esql(
        es,
        args.user,
        args.password,
        """
FROM metrics-aws.ec2_metrics-default
| WHERE @timestamp >= NOW() - 24 hours
| STATS avg_cpu = AVG(`aws.ec2.metrics.CPUUtilization.avg`),
        max_cpu = MAX(`aws.ec2.metrics.CPUUtilization.avg`),
        status_fail = MAX(`aws.ec2.metrics.StatusCheckFailed.avg`),
        samples = COUNT(*)
  BY instance = COALESCE(cloud.instance.name, cloud.instance.id),
     az = cloud.availability_zone,
     type = cloud.machine.type,
     account = cloud.account.id,
     region = cloud.region
| WHERE samples >= 1
""".strip(),
    )

    for row in ec2:
        name = row.get("instance") or "unknown"
        avg = float(row.get("avg_cpu") or 0)
        fail = float(row.get("status_fail") or 0)
        cloud = {
            "availability_zone": row.get("az"),
            "account": {"id": row.get("account")},
            "region": row.get("region"),
        }

        if fail and fail > 0:
            docs.append(
                (
                    f"{name}-status_check-{stamp}",
                    {
                        "@timestamp": now,
                        "category": "performance_risk",
                        "severity": "high",
                        "metric_name": "status_check_failed",
                        "metric_value": fail,
                        "threshold": 0,
                        "recommendation": (
                            f"EC2 instance {name} is failing status checks "
                            f"(StatusCheckFailed avg {fail} over 24h) — investigate "
                            "instance / system health before relying on this host."
                        ),
                        "resource": {"type": "ec2_instance", "name": name},
                        "cloud": cloud,
                    },
                )
            )

        if avg < CPU_LOW:
            docs.append(
                (
                    f"{name}-cost_optimization-{stamp}",
                    {
                        "@timestamp": now,
                        "category": "cost_optimization",
                        "severity": "medium",
                        "metric_name": "avg_cpu_pct",
                        "metric_value": avg,
                        "threshold": CPU_LOW,
                        "recommendation": (
                            f"EC2 instance {name} ({row.get('type') or 'unknown type'}) is underutilized "
                            f"(avg CPU {avg:.2f}% over 24h) — consider downsizing or stopping "
                            "this instance to save cost."
                        ),
                        "resource": {"type": "ec2_instance", "name": name},
                        "cloud": cloud,
                    },
                )
            )
        elif avg > CPU_HIGH:
            docs.append(
                (
                    f"{name}-performance_risk-{stamp}",
                    {
                        "@timestamp": now,
                        "category": "performance_risk",
                        "severity": "high",
                        "metric_name": "avg_cpu_pct",
                        "metric_value": avg,
                        "threshold": CPU_HIGH,
                        "recommendation": (
                            f"EC2 instance {name} is running near capacity "
                            f"(avg CPU {avg:.2f}% over 24h) — consider resizing to a larger "
                            "instance type to avoid throttling or outages."
                        ),
                        "resource": {"type": "ec2_instance", "name": name},
                        "cloud": cloud,
                    },
                )
            )

    # Empty / near-empty S3 buckets
    s3 = esql(
        es,
        args.user,
        args.password,
        """
FROM metrics-aws.s3_daily_storage-default
| WHERE @timestamp >= NOW() - 7 days
| STATS size = MAX(`aws.s3_daily_storage.bucket.size.bytes`),
        objects = MAX(`aws.s3_daily_storage.number_of_objects`)
  BY bucket = `aws.s3.bucket.name`,
     region = cloud.region,
     account = cloud.account.id
""".strip(),
    )
    for row in s3:
        size = int(row.get("size") or 0)
        objects = row.get("objects")
        objects_n = int(objects) if objects is not None else None
        if size > 0 and (objects_n is None or objects_n > 0):
            continue
        name = row.get("bucket") or "unknown"
        docs.append(
            (
                f"{name}-empty_bucket-{stamp}",
                {
                    "@timestamp": now,
                    "category": "cost_optimization",
                    "severity": "low",
                    "metric_name": "s3_bucket_size_bytes",
                    "metric_value": size,
                    "threshold": 0,
                    "recommendation": (
                        f"S3 bucket {name} appears empty "
                        f"(size={size} bytes"
                        + (f", objects={objects_n}" if objects_n is not None else "")
                        + ") — confirm it is still needed or remove it to reduce clutter and "
                        "accidental exposure risk."
                    ),
                    "resource": {"type": "s3_bucket", "name": name},
                    "cloud": {
                        "region": row.get("region"),
                        "account": {"id": row.get("account")},
                    },
                },
            )
        )

    if not docs:
        print("No recommendations generated from current metrics.", file=sys.stderr)
        return 0

    # Bulk index
    bulk_lines = []
    for doc_id, body in docs:
        bulk_lines.append(json.dumps({"index": {"_index": INDEX, "_id": doc_id}}))
        bulk_lines.append(json.dumps(body))
    payload = ("\n".join(bulk_lines) + "\n").encode()
    headers = {
        "Authorization": "Basic " + b64encode(f"{args.user}:{args.password}".encode()).decode(),
        "Content-Type": "application/x-ndjson",
    }
    request = urllib.request.Request(f"{es}/_bulk", data=payload, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=120) as resp:
        result = json.loads(resp.read().decode())
    if result.get("errors"):
        failed = [i for i in result.get("items", []) if "error" in i.get("index", {})]
        print(f"Bulk completed with errors: {len(failed)}", file=sys.stderr)
        print(json.dumps(failed[:3], indent=2), file=sys.stderr)
        return 1

    # Refresh
    req("POST", f"{es}/{INDEX}/_refresh", args.user, args.password)
    print(f"Indexed {len(docs)} recommendations into {INDEX}")
    by_cat: dict[str, int] = {}
    for _, body in docs:
        by_cat[body["category"]] = by_cat.get(body["category"], 0) + 1
    print(json.dumps(by_cat, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
