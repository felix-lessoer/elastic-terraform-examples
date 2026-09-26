#!/usr/bin/env python3
"""Generate azure-cockpit-recommendations from live Azure metrics.

Mirrors the GCP/AWS concept behind `gcp-cockpit-recommendations`:
  - cost_optimization: underutilized VMs (avg CPU < 5% / 24h), near-empty storage accounts
  - performance_risk: hot VMs (avg CPU > 85%), 

Usage:
  python3 generate_azure_recommendations.py \\
    --es-url https://azure-observability-cockpit-....es....elastic.cloud \\
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


INDEX = "azure-cockpit-recommendations"
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

    # Azure VM CPU
    vms = esql(
        es,
        args.user,
        args.password,
        """
FROM metrics-azure.compute_vm-default
| WHERE @timestamp >= NOW() - 24 hours
| STATS avg_cpu = AVG(azure.compute_vm.percentage_cpu.avg),
        max_cpu = MAX(azure.compute_vm.percentage_cpu.avg),
        samples = COUNT(*)
  BY vm = COALESCE(azure.resource.name, cloud.instance.name, cloud.instance.id),
     resource_group = azure.resource.group,
     account = cloud.account.id,
     region = cloud.region
| WHERE samples >= 1
""".strip(),
    )

    for row in vms:
        name = row.get("vm") or "unknown"
        avg = float(row.get("avg_cpu") or 0)
        cloud = {
            "account": {"id": row.get("account")},
            "region": row.get("region"),
        }

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
                            f"Virtual machine {name} in resource group "
                            f"{row.get('resource_group') or 'unknown'} is underutilized "
                            f"(avg CPU {avg:.2f}% over 24h) — consider downsizing or "
                            "deallocating to save cost."
                        ),
                        "resource": {"type": "azure_vm", "name": name},
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
                            f"Virtual machine {name} is running near capacity "
                            f"(avg CPU {avg:.2f}% over 24h) — consider resizing to a larger "
                            "SKU or scaling out."
                        ),
                        "resource": {"type": "azure_vm", "name": name},
                        "cloud": cloud,
                    },
                )
            )

    # Near-empty storage accounts
    storage = esql(
        es,
        args.user,
        args.password,
        """
FROM metrics-azure.storage_account-default
| WHERE @timestamp >= NOW() - 7 days
| STATS size = MAX(COALESCE(azure.storage_account.used_capacity.avg, azure.storage_account.used_capacity.total))
  BY account_name = COALESCE(azure.resource.name, azure.storage_account.name),
     resource_group = azure.resource.group,
     region = cloud.region,
     account = cloud.account.id
""".strip(),
    )
    for row in storage:
        size = int(float(row.get("size") or 0))
        if size >= 1048576:
            continue
        name = row.get("account_name") or "unknown"
        docs.append(
            (
                f"{name}-empty_storage-{stamp}",
                {
                    "@timestamp": now,
                    "category": "cost_optimization",
                    "severity": "low",
                    "metric_name": "storage_used_capacity_bytes",
                    "metric_value": size,
                    "threshold": 1048576,
                    "recommendation": (
                        f"Storage account {name} in resource group "
                        f"{row.get('resource_group') or 'unknown'} appears near-empty "
                        f"(used capacity={size} bytes) — confirm it is still needed or "
                        "remove it to reduce clutter and exposure risk."
                    ),
                    "resource": {"type": "azure_storage_account", "name": name},
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
