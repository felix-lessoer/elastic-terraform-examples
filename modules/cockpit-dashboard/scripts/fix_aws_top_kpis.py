#!/usr/bin/env python3
"""Fix AWS cockpit top-row KPI panels that fail without working CPS.

The Observability project reports CPS link status=enabled, but ES|QL cannot
resolve the Security project alias (`no_matching_project_exception`). Panels
that queried `.alerts-security.alerts-default` or
`aws-observe-and-protect-ad5bcf:…` therefore error in the UI.

Rewrite the four absolute-y=4 metric panels to Observability-local indices
that execute cleanly, preserving labels where the data still exists locally.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NDJSON = ROOT / "cockpit-aws.ndjson"

# panelIndex → replacement ES|QL layer config
KPI_FIXES = {
    # was: Security Alerts (Active) on .alerts-security.alerts-default
    "1dfcd0c5-db92-46ee-a0cc-6b38079265ab": {
        "label": "Active datasets",
        "esql": (
            "FROM logs-*, metrics-*\n"
            "| WHERE @timestamp >= ?_tstart AND @timestamp < ?_tend\n"
            "| STATS `Active datasets` = COUNT_DISTINCT(data_stream.dataset)"
        ),
        "index": "logs-*,metrics-*-@timestamp",
        "time_field": "@timestamp",
        "field_name": "Active datasets",
    },
    # was: High/Critical Alerts on .alerts-security.alerts-default
    "99c28cc1-a686-482b-9fc9-2cf7869b7b5b": {
        "label": "Hosts delivering",
        "esql": (
            "FROM logs-*, metrics-*\n"
            "| WHERE @timestamp >= ?_tstart AND @timestamp < ?_tend\n"
            "| STATS `Hosts delivering` = COUNT_DISTINCT(host.name)"
        ),
        "index": "logs-*,metrics-*-@timestamp",
        "time_field": "@timestamp",
        "field_name": "Hosts delivering",
    },
    # was: Critical ML Anomalies with broken CPS dual-index
    "d170a127-afff-4154-b6c3-24a85a931382": {
        "label": "Critical ML Anomalies",
        "esql": (
            "FROM .ml-anomalies-shared-000001\n"
            "| WHERE record_score >= 75 AND timestamp >= ?_tstart AND timestamp < ?_tend\n"
            "| STATS `Critical ML Anomalies` = COUNT(*)"
        ),
        "index": ".ml-anomalies-shared-000001-timestamp",
        "time_field": "timestamp",
        "field_name": "Critical ML Anomalies",
    },
    # was: CSPM findings via broken CPS qualifier
    "143696f7-f91e-41b2-9650-40b28c80a105": {
        "label": "CSPM findings",
        "esql": (
            "FROM security_solution-*.misconfiguration_latest\n"
            "| STATS `CSPM findings` = COUNT(*)"
        ),
        "index": "security_solution-*.misconfiguration_latest",
        "time_field": "@timestamp",
        "field_name": "CSPM findings",
        "title": "CSPM findings",
    },
}


def patch_panel(panel: dict, fix: dict) -> None:
    ec = panel.setdefault("embeddableConfig", {})
    if fix.get("title") is not None:
        ec["title"] = fix["title"]
    attrs = ec.setdefault("attributes", {})
    if fix.get("title") is not None:
        attrs["title"] = fix["title"]
    state = attrs.setdefault("state", {})
    layers = (
        state.setdefault("datasourceStates", {})
        .setdefault("textBased", {})
        .setdefault("layers", {})
    )
    if not layers:
        raise ValueError(f"panel {panel.get('panelIndex')} has no textBased layers")
    # Prefer layer_0 when present
    layer_id = "layer_0" if "layer_0" in layers else next(iter(layers))
    layer = layers[layer_id]
    layer["index"] = fix["index"]
    layer["timeField"] = fix["time_field"]
    layer["query"] = {"esql": fix["esql"]}
    cols = layer.get("columns") or []
    if cols:
        cols[0]["fieldName"] = fix["field_name"]
        cols[0]["label"] = fix["label"]
        cols[0]["customLabel"] = True
        cols[0].setdefault("meta", {})["type"] = "number"
    else:
        layer["columns"] = [
            {
                "columnId": "metric_accessor_metric",
                "fieldName": fix["field_name"],
                "label": fix["label"],
                "customLabel": True,
                "meta": {"type": "number"},
            }
        ]
    state["internalReferences"] = [
        {
            "type": "index-pattern",
            "id": fix["index"],
            "name": f"indexpattern-datasource-layer-{layer_id}",
        }
    ]


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else NDJSON
    lines = path.read_text().splitlines(keepends=True)
    out: list[str] = []
    patched = 0
    for line in lines:
        raw = line.strip()
        if not raw:
            out.append(line)
            continue
        obj = json.loads(raw)
        attrs = obj.get("attributes") or {}
        if "panelsJSON" not in attrs:
            out.append(line if line.endswith("\n") else line + "\n")
            continue
        panels = json.loads(attrs["panelsJSON"])
        for p in panels:
            pid = p.get("panelIndex")
            if pid in KPI_FIXES:
                patch_panel(p, KPI_FIXES[pid])
                patched += 1
        attrs["panelsJSON"] = json.dumps(panels, separators=(",", ":"))
        obj["attributes"] = attrs
        out.append(json.dumps(obj, separators=(",", ":")) + "\n")
    if patched != len(KPI_FIXES):
        raise SystemExit(f"expected to patch {len(KPI_FIXES)} panels, patched {patched}")
    path.write_text("".join(out))
    print(f"patched {patched} top KPI panels in {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
