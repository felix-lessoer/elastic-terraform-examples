#!/usr/bin/env python3
"""Shared helpers for multi-cloud cockpit insight fabric (AWS / GCP / Azure)."""

from __future__ import annotations

import json
import sys
import time
import uuid
from base64 import b64encode
from datetime import datetime, timezone
from typing import Any
from urllib import error, request

# ---------------------------------------------------------------------------
# Elasticsearch helpers
# ---------------------------------------------------------------------------


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


def uid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Coverage seeding
# ---------------------------------------------------------------------------


def absorb_dataset_stats(dataset_stats: dict[str, dict], rows: list[dict]) -> None:
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


def collect_dataset_stats(
    obs_es: str,
    sec_es: str,
    obs_user: str,
    obs_pass: str,
    sec_user: str,
    sec_pass: str,
    probes: list[tuple[str, str, str, list[str]]],
) -> dict[str, dict]:
    """probes: list of (es, user, pw, [index_patterns])."""
    dataset_stats: dict[str, dict] = {}
    for es, user, pw in (
        (obs_es, obs_user, obs_pass),
        (sec_es, sec_user, sec_pass),
    ):
        absorb_dataset_stats(
            dataset_stats,
            esql(
                es,
                user,
                pw,
                """FROM logs-*, metrics-*
| WHERE @timestamp > NOW() - 7 days
| STATS docs = COUNT(*), last_seen = MAX(@timestamp) BY data_stream.dataset
| SORT docs DESC
| LIMIT 200""",
            ),
        )
    for es, user, pw, patterns in probes:
        for pattern in patterns:
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
                    # best-effort infer from pattern
                    ds = (
                        pattern.replace("metrics-", "")
                        .replace("logs-", "")
                        .replace("*", "")
                        .rstrip("-default")
                    )
                if ds and (row.get("docs") or 0) > 0:
                    absorb_dataset_stats(
                        dataset_stats,
                        [
                            {
                                "data_stream.dataset": ds,
                                "docs": row.get("docs") or 0,
                                "last_seen": row.get("last_seen"),
                            }
                        ],
                    )
    return dataset_stats


def build_coverage_docs(
    service_catalog: list[dict],
    dataset_stats: dict[str, dict],
    *,
    optional_services: set[str] | None = None,
    stale_after: dict[str, float] | None = None,
) -> list[tuple[str, dict]]:
    optional_services = optional_services or set()
    stale_after = stale_after or {}
    docs = []
    ts = now_iso()
    for svc in service_catalog:
        matched = [dataset_stats[d] for d in svc["datasets"] if d in dataset_stats]
        docs_24h = int(sum((m.get("docs") or 0) for m in matched))
        last_seen = None
        for m in matched:
            ls = m.get("last_seen")
            if ls and (last_seen is None or str(ls) > str(last_seen)):
                last_seen = ls
        if docs_24h > 0:
            status = "healthy"
            detail = f"{docs_24h} docs"
        elif svc["service"] in optional_services:
            status = "not_configured"
            detail = "integration not enabled"
        else:
            status = "missing"
            detail = "no data yet"
        if last_seen and status == "healthy":
            try:
                if isinstance(last_seen, (int, float)):
                    age_h = (time.time() * 1000 - float(last_seen)) / 3600000
                else:
                    age_h = (
                        datetime.now(timezone.utc)
                        - datetime.fromisoformat(str(last_seen).replace("Z", "+00:00"))
                    ).total_seconds() / 3600
                threshold = stale_after.get(svc["service"], 8)
                if age_h > threshold:
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
    return docs


COVERAGE_MAPPINGS = {
    "@timestamp": {"type": "date"},
    "service": {"type": "keyword"},
    "label": {"type": "keyword"},
    "category": {"type": "keyword"},
    "status": {"type": "keyword"},
    "docs_24h": {"type": "long"},
    "last_seen": {"type": "date"},
    "datasets": {"type": "keyword"},
    "detail": {"type": "keyword"},
}

ASSETS_MAPPINGS = {
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
            "project": {"properties": {"id": {"type": "keyword"}}},
            "machine": {"properties": {"type": {"type": "keyword"}}},
        }
    },
    "metric_name": {"type": "keyword"},
    "metric_value": {"type": "double"},
    "last_seen": {"type": "date"},
}

EVENTS_MAPPINGS = {
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
}

SECURITY_KPI_MAPPINGS = {
    "@timestamp": {"type": "date"},
    "kpi_id": {"type": "keyword"},
    "active_alerts": {"type": "long"},
    "high_critical_alerts": {"type": "long"},
    "cspm_findings": {"type": "long"},
    "audit_24h": {"type": "long"},
    "firewall_24h": {"type": "long"},
    "activity_24h": {"type": "long"},
    "platform_24h": {"type": "long"},
    "cloudtrail_24h": {"type": "long"},
    "health_events": {"type": "long"},
}


# ---------------------------------------------------------------------------
# custom_content Liquid templates (Datadog-comparable)
# ---------------------------------------------------------------------------


def scoreboard_template(cloud_label: str, subtitle: str) -> str:
    return f"""<html>
<head>
<style>
  body {{ margin:0; padding: var(--cc-space-l); font-family: var(--cc-font-family); color: var(--cc-color-text); background: var(--cc-color-background); box-sizing:border-box; }}
  .wrap {{ display:flex; flex-direction:column; gap: var(--cc-space-m); }}
  .hero {{ display:flex; justify-content:space-between; gap: var(--cc-space-l); align-items:center; padding: var(--cc-space-m) var(--cc-space-xl); border-radius: var(--cc-radius); background: linear-gradient(135deg,#0b1f3a 0%,#16324f 55%,#1e3a5f 100%); color:#fff; box-shadow:0 2px 12px rgba(0,0,0,.18); }}
  .kicker {{ font-size:.6875rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:#48EFCF; }}
  .title {{ font-size:1.125rem; font-weight:600; }}
  .sub {{ font-size:.8125rem; color:rgba(255,255,255,.78); }}
  .grid {{ display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: var(--cc-space-m); }}
  .card {{ background: var(--cc-color-surface); border:1px solid var(--cc-color-border); border-radius: var(--cc-radius); padding: var(--cc-space-m); box-shadow:0 1px 2px rgba(0,0,0,.04); }}
  .card .label {{ font-size:.75rem; font-weight:700; letter-spacing:.04em; text-transform:uppercase; opacity:.7; }}
  .card .value {{ font-size:1.75rem; font-weight:700; margin-top: var(--cc-space-xs); color:#0B64DD; }}
  .card .hint {{ font-size:.75rem; opacity:.65; margin-top: var(--cc-space-xs); }}
  .sev-high .value {{ color:#FF957D; }}
  .sev-ok .value {{ color:#209280; }}
  @media (max-width:900px){{ .grid{{ grid-template-columns:1fr 1fr; }} .hero{{ flex-direction:column; align-items:flex-start; }} }}
</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <div>
      <div class="kicker">Insight fabric</div>
      <div class="title">{cloud_label} posture at a glance</div>
      <div class="sub">{subtitle}</div>
    </div>
  </div>
  <div class="grid">
    {{% assign row = rows[0] %}}
    <div class="card sev-high">
      <div class="label">Active alerts</div>
      <div class="value">{{{{ row["active_alerts"].value | default: 0 }}}}</div>
      <div class="hint">From Security detection engine</div>
    </div>
    <div class="card sev-high">
      <div class="label">High / critical</div>
      <div class="value">{{{{ row["high_critical_alerts"].value | default: 0 }}}}</div>
      <div class="hint">Prioritize these first</div>
    </div>
    <div class="card">
      <div class="label">Audit / activity (24h)</div>
      <div class="value">{{{{ row["audit_24h"].value | default: row["activity_24h"].value | default: row["cloudtrail_24h"].value | default: 0 }}}}</div>
      <div class="hint">Management / control-plane volume</div>
    </div>
    <div class="card sev-ok">
      <div class="label">CSPM findings</div>
      <div class="value">{{{{ row["cspm_findings"].value | default: 0 }}}}</div>
      <div class="hint">Latest posture snapshot</div>
    </div>
  </div>
</div>
</body>
</html>
"""


MATRIX_TMPL = """<html>
<head>
<style>
  body { margin:0; padding: var(--cc-space-l); font-family: var(--cc-font-family); color: var(--cc-color-text); background: var(--cc-color-background); }
  .wrap { display:flex; flex-direction:column; gap: var(--cc-space-m); }
  .head { display:flex; justify-content:space-between; align-items:baseline; gap: var(--cc-space-m); }
  .title { font-size:1rem; font-weight:700; }
  .sub { font-size:.8125rem; opacity:.7; }
  .grid { display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: var(--cc-space-s); }
  .tile { border:1px solid var(--cc-color-border); border-radius: var(--cc-radius); background: var(--cc-color-surface); padding: var(--cc-space-m); min-height: 5.5rem; display:flex; flex-direction:column; gap: .35rem; }
  .tile .name { font-weight:700; font-size:.875rem; }
  .tile .meta { font-size:.75rem; opacity:.65; }
  .badge { align-self:flex-start; font-size:.625rem; font-weight:700; letter-spacing:.06em; text-transform:uppercase; padding:2px 8px; border-radius: var(--cc-radius-s); border:1px solid var(--cc-color-border); }
  .healthy { background: rgba(32,146,128,.12); color:#176655; border-color: rgba(32,146,128,.35); }
  .stale { background: rgba(254,197,20,.18); color:#8a6a00; border-color: rgba(254,197,20,.45); }
  .missing { background: rgba(255,149,125,.15); color:#9b3b2a; border-color: rgba(255,149,125,.4); }
  .not_configured { background: rgba(11,100,221,.08); color:#0B64DD; border-color: rgba(11,100,221,.28); }
  @media (max-width:900px){ .grid{ grid-template-columns:1fr 1fr; } }
</style>
</head>
<body>
<div class="wrap">
  <div class="head">
    <div class="title">Service coverage</div>
    <div class="sub">Healthy = telemetry in last window · comparable to Datadog cloud overview tiles</div>
  </div>
  <div class="grid">
    {% for row in rows %}
      {% assign status = row["status"].value %}
      <div class="tile">
        <span class="badge {{ status }}">{{ status }}</span>
        <div class="name">{{ row["label"].value }}</div>
        <div class="meta">{{ row["detail"].value }}</div>
        <div class="meta">{{ row["category"].value }}</div>
      </div>
    {% endfor %}
  </div>
</div>
</body>
</html>
"""

TIMELINE_TMPL = """<html>
<head>
<style>
  body { margin:0; padding: var(--cc-space-l); font-family: var(--cc-font-family); color: var(--cc-color-text); background: var(--cc-color-background); }
  .wrap { display:flex; flex-direction:column; gap: var(--cc-space-m); }
  .title { font-size:1rem; font-weight:700; }
  .sub { font-size:.8125rem; opacity:.7; margin-bottom: var(--cc-space-s); }
  .list { display:flex; flex-direction:column; gap: .4rem; }
  .item { display:grid; grid-template-columns: 7rem 1fr auto; gap: var(--cc-space-m); align-items:center; padding: .55rem .75rem; border:1px solid var(--cc-color-border); border-radius: var(--cc-radius-s); background: var(--cc-color-surface); text-decoration:none; color:inherit; }
  .item:hover { border-color:#0B64DD; transform: translateX(2px); }
  .src { font-size:.6875rem; font-weight:700; letter-spacing:.05em; text-transform:uppercase; opacity:.65; }
  .ttl { font-size:.875rem; font-weight:600; }
  .dtl { font-size:.75rem; opacity:.7; }
  .sev { font-size:.625rem; font-weight:700; text-transform:uppercase; padding:2px 8px; border-radius: var(--cc-radius-s); border:1px solid var(--cc-color-border); }
  .high,.critical { color:#9b3b2a; background: rgba(255,149,125,.15); }
  .medium { color:#8a6a00; background: rgba(254,197,20,.18); }
  .info,.low { color:#176655; background: rgba(32,146,128,.12); }
  .empty { padding: var(--cc-space-l); text-align:center; opacity:.7; font-size:.875rem; }
</style>
</head>
<body>
<div class="wrap">
  <div class="title">What changed</div>
  <div class="sub">Control-plane highlights · recommendation churn</div>
  <div class="list">
    {% if rows.size == 0 %}
      <div class="empty">No insight events yet — run the insight seeder / wait for the next workflow cycle.</div>
    {% endif %}
    {% for row in rows %}
      <a class="item" href="{{ row["link"].value | default: '#' }}">
        <div class="src">{{ row["event.source"].value }}</div>
        <div>
          <div class="ttl">{{ row["title"].value }}</div>
          <div class="dtl">{{ row["detail"].value }}</div>
        </div>
        <span class="sev {{ row["event.severity"].value }}">{{ row["event.severity"].value }}</span>
      </a>
    {% endfor %}
  </div>
</div>
</body>
</html>
"""


def custom_panel(*, panel_id: str, template: str, esql_query: str | None, grid: dict) -> dict:
    cfg: dict = {
        "hide_title": True,
        "hide_border": True,
        "template": template,
    }
    if esql_query:
        cfg["esql_query"] = [esql_query]
    g = dict(grid)
    g["i"] = panel_id
    return {
        "type": "custom_content",
        "panelIndex": panel_id,
        "gridData": g,
        "embeddableConfig": cfg,
    }
