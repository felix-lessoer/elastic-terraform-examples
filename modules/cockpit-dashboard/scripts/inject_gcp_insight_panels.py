#!/usr/bin/env python3
"""Inject Datadog-comparable insight panels into cockpit.ndjson (GCP)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NDJSON = ROOT / "cockpit.ndjson"

from build_aws_cockpit_ndjson import (  # noqa: E402
    esql_metric_panel,
    esql_table_panel,
    esql_xy_panel,
)
from insight_fabric_common import (  # noqa: E402
    MATRIX_TMPL,
    TIMELINE_TMPL,
    custom_panel,
    scoreboard_template,
    uid,
)
from fabric_drilldowns import DRILLDOWN_IDS, drilldowns_panel  # noqa: E402
from ootb_nav import NAV_HEIGHT, PANEL_IDS, inject_ootb_nav  # noqa: E402

DRILLDOWN_H = 4

SCOREBOARD_ID = "c0ffee10-6ee2-4c91-94f8-f034e8d34510"
MATRIX_ID = "c0ffee11-6ee2-4c91-94f8-f034e8d34511"
TIMELINE_ID = "c0ffee12-6ee2-4c91-94f8-f034e8d34512"
SUMMARY_ID = "c0ffee13-6ee2-4c91-94f8-f034e8d34513"
INVENTORY_IDS = (
    "c0ffee20-6ee2-4c91-94f8-f034e8d34520",
    "c0ffee21-6ee2-4c91-94f8-f034e8d34521",
    "c0ffee22-6ee2-4c91-94f8-f034e8d34522",
)

TOP_KPI_IDS = {
    "1dfcd0c5-db92-46ee-a0cc-6b38079265ab",
    "99c28cc1-a686-482b-9fc9-2cf7869b7b5b",
    "d170a127-afff-4154-b6c3-24a85a931382",
    "9d6ad208-6370-4b1b-8471-42bacd4763c7",
    "143696f7-f91e-41b2-9650-40b28c80a105",
}

KPI_INDEX = "gcp-cockpit-security-kpi"
ASSETS_INDEX = "gcp-cockpit-assets"
SUMMARY_INDEX = "gcp-cockpit-insight-summary"


def build_top_kpis() -> list[dict]:
    return [
        esql_metric_panel(
            title="",
            metric_label="Security Alerts (Active)",
            esql=(
                f"FROM {KPI_INDEX}\n"
                "| SORT @timestamp DESC\n"
                "| LIMIT 1\n"
                "| STATS `Security Alerts (Active)` = MAX(active_alerts)"
            ),
            index=KPI_INDEX,
            grid={"x": 0, "y": 4, "w": 12, "h": 4},
            panel_id="1dfcd0c5-db92-46ee-a0cc-6b38079265ab",
        ),
        esql_metric_panel(
            title="",
            metric_label="High/Critical Alerts",
            esql=(
                f"FROM {KPI_INDEX}\n"
                "| SORT @timestamp DESC\n"
                "| LIMIT 1\n"
                "| STATS `High/Critical Alerts` = MAX(high_critical_alerts)"
            ),
            index=KPI_INDEX,
            grid={"x": 12, "y": 4, "w": 12, "h": 4},
            panel_id="99c28cc1-a686-482b-9fc9-2cf7869b7b5b",
        ),
        esql_metric_panel(
            title="",
            metric_label="Critical ML Anomalies",
            esql=(
                "FROM .ml-anomalies-shared-000001\n"
                "| WHERE record_score >= 75 AND timestamp >= ?_tstart AND timestamp < ?_tend\n"
                "| STATS `Critical ML Anomalies` = COUNT(*)"
            ),
            index=".ml-anomalies-shared-000001-timestamp",
            grid={"x": 24, "y": 4, "w": 12, "h": 4},
            panel_id="d170a127-afff-4154-b6c3-24a85a931382",
        ),
        esql_metric_panel(
            title="",
            metric_label="CSPM findings",
            esql=(
                f"FROM {KPI_INDEX}\n"
                "| SORT @timestamp DESC\n"
                "| LIMIT 1\n"
                "| STATS `CSPM findings` = MAX(cspm_findings)"
            ),
            index=KPI_INDEX,
            grid={"x": 36, "y": 4, "w": 12, "h": 4},
            panel_id="9d6ad208-6370-4b1b-8471-42bacd4763c7",
        ),
    ]


def scrub(panel: dict, cps_prefixes: tuple[str, ...] = ()) -> dict:
    raw = json.dumps(panel)
    for prefix in cps_prefixes:
        normalized = prefix.strip().rstrip(":")
        if not normalized:
            continue
        raw = raw.replace(
            f"{normalized}:security_solution-cloud_security_posture.misconfiguration_latest",
            "security_solution-*.misconfiguration_latest",
        )
        raw = raw.replace(
            f".ml-anomalies-shared-000001,{normalized}:.ml-anomalies-shared-000001",
            ".ml-anomalies-shared-000001",
        )
        raw = raw.replace(f'"{normalized}:', '"')
    return json.loads(raw)


def rebuild_inventory_panels(y: int) -> list[dict]:
    return [
        esql_xy_panel(
            title="Assets by type",
            x_field="Resource Type",
            y_field="Count",
            esql=(
                f"FROM {ASSETS_INDEX}\n"
                "| STATS `Count` = COUNT(*) BY `Resource Type` = resource.type\n"
                "| SORT `Count` DESC\n"
                "| LIMIT 15"
            ),
            index=ASSETS_INDEX,
            grid={"x": 0, "y": y, "w": 16, "h": 14},
            panel_id=INVENTORY_IDS[0],
        ),
        esql_xy_panel(
            title="Top assets by name",
            x_field="Resource Name",
            y_field="Count",
            esql=(
                f"FROM {ASSETS_INDEX}\n"
                "| STATS `Count` = COUNT(*) BY `Resource Name` = resource.name\n"
                "| SORT `Count` DESC\n"
                "| LIMIT 15"
            ),
            index=ASSETS_INDEX,
            grid={"x": 16, "y": y, "w": 16, "h": 14},
            panel_id=INVENTORY_IDS[1],
        ),
        esql_xy_panel(
            title="GCE by zone",
            x_field="Zone",
            y_field="Instances",
            esql=(
                f"FROM {ASSETS_INDEX}\n"
                '| WHERE resource.type == "gce_instance"\n'
                "| STATS `Instances` = COUNT(*) BY `Zone` = cloud.availability_zone\n"
                "| SORT `Instances` DESC\n"
                "| LIMIT 15"
            ),
            index=ASSETS_INDEX,
            grid={"x": 32, "y": y, "w": 16, "h": 14},
            panel_id=INVENTORY_IDS[2],
        ),
    ]


def inject(panels: list[dict], cps_prefixes: tuple[str, ...] = ()) -> list[dict]:
    drop_ids = set(TOP_KPI_IDS) | set(INVENTORY_IDS) | {
        SCOREBOARD_ID,
        MATRIX_ID,
        TIMELINE_ID,
        SUMMARY_ID,
        DRILLDOWN_IDS["gcp"],
        PANEL_IDS["gcp"],
    }
    drop_titles = {
        "Assets by type",
        "Top assets by name",
        "Findings by evaluation",
        "GCE by zone",
        "CSPM findings",
        "CSPM findings (24h)",
    }
    kept = []
    for p in panels:
        if p.get("panelIndex") in drop_ids:
            continue
        title = (p.get("embeddableConfig") or {}).get("title") or ""
        attrs_title = ((p.get("embeddableConfig") or {}).get("attributes") or {}).get("title") or ""
        if title in drop_titles or attrs_title in drop_titles:
            continue
        kept.append(scrub(p, cps_prefixes))

    kept = inject_ootb_nav(kept, "gcp", y=8)
    insight_y = 8 + NAV_HEIGHT
    summary_h, scoreboard_h, matrix_h = 10, 8, 14
    scoreboard_y = insight_y + summary_h
    drill_y = scoreboard_y + scoreboard_h
    matrix_y = drill_y + DRILLDOWN_H
    insight_end = matrix_y + matrix_h

    scoreboard = custom_panel(
        panel_id=SCOREBOARD_ID,
        template=scoreboard_template(
            "GCP",
            "Security KPIs mirrored from the Security project · coverage & recommendations computed by workflows",
            cards=[
                {
                    "label": "Active alerts",
                    "field": "active_alerts",
                    "hint": "Open Security alerts →",
                    "href": "/app/security/alerts",
                    "sev": "sev-high",
                },
                {
                    "label": "High / critical",
                    "field": "high_critical_alerts",
                    "hint": "Prioritize these first →",
                    "href": "/app/security/alerts",
                    "sev": "sev-high",
                },
                {
                    "label": "Audit (24h)",
                    "field": "audit_24h",
                    "hint": "Open Audit dashboard →",
                    "href": "/app/dashboards#/view/gcp-48e12760-cbe4-11ec-b519-85ccf621cbbf",
                    "sev": "",
                },
                {
                    "label": "CSPM findings",
                    "field": "cspm_findings",
                    "hint": "Open CSPM findings →",
                    "href": "/app/security/cloud_security_posture/findings/misconfigurations",
                    "sev": "sev-ok",
                },
            ],
        ),
        esql_query=f"FROM {KPI_INDEX}\n| SORT @timestamp DESC\n| LIMIT 1",
        grid={"x": 0, "y": scoreboard_y, "w": 48, "h": scoreboard_h},
    )
    summary = esql_table_panel(
        panel_id=SUMMARY_ID,
        title="Insight Engine — Agent summary",
        esql=(
            f"FROM {SUMMARY_INDEX}\n"
            "| SORT @timestamp DESC\n"
            "| LIMIT 1\n"
            "| KEEP @timestamp, priority, headline, summary, action_1, action_2, action_3"
        ),
        index=f"{SUMMARY_INDEX}-@timestamp",
        columns=[
            ("@timestamp", "date"),
            ("priority", "string"),
            ("headline", "string"),
            ("summary", "string"),
            ("action_1", "string"),
            ("action_2", "string"),
            ("action_3", "string"),
        ],
        grid={"x": 0, "y": insight_y, "w": 48, "h": summary_h},
    )
    drilldowns = drilldowns_panel("gcp", y=drill_y, h=DRILLDOWN_H)
    matrix = custom_panel(
        panel_id=MATRIX_ID,
        template=MATRIX_TMPL,
        esql_query=(
            "FROM gcp-cockpit-coverage\n"
            '| WHERE category IN ("compute", "storage", "cost", "network", "platform", "security", "data")\n'
            "| SORT category ASC, label ASC\n"
            "| LIMIT 20"
        ),
        grid={"x": 0, "y": matrix_y, "w": 28, "h": matrix_h},
    )
    timeline = custom_panel(
        panel_id=TIMELINE_ID,
        template=TIMELINE_TMPL,
        esql_query="FROM gcp-cockpit-events\n| SORT @timestamp DESC\n| LIMIT 12",
        grid={"x": 28, "y": matrix_y, "w": 20, "h": matrix_h},
    )

    chrome_ids = {PANEL_IDS["gcp"]} | TOP_KPI_IDS
    section_panels = [p for p in kept if (p.get("gridData") or {}).get("sectionId")]
    header_panels = [
        p
        for p in kept
        if not (p.get("gridData") or {}).get("sectionId")
        and (
            p.get("panelIndex") in chrome_ids
            or int((p.get("gridData") or {}).get("y") or 0) < 8
        )
    ]
    body_panels = [
        p
        for p in kept
        if p not in section_panels
        and p not in header_panels
        and p.get("panelIndex") != PANEL_IDS["gcp"]
    ]

    inventory_md = (
        "### GCP inventory (live metrics assets)\n"
        "Charts below query `gcp-cockpit-assets`, refreshed by the "
        "**GCP Cockpit Asset Inventory** workflow and the insight seeder.\n"
    )
    for p in body_panels + section_panels:
        cfg = p.get("embeddableConfig") or {}
        content = cfg.get("content") or ""
        if "inventory" in content.lower() and "###" in content:
            cfg["content"] = inventory_md

    body_panels.sort(
        key=lambda p: (
            int((p.get("gridData") or {}).get("y") or 0),
            int((p.get("gridData") or {}).get("x") or 0),
        )
    )
    if body_panels:
        min_body_y = min(int((p.get("gridData") or {}).get("y") or 0) for p in body_panels)
        shift = insight_end - min_body_y
        if shift != 0:
            for p in body_panels:
                gd = p.get("gridData") or {}
                gd["y"] = int(gd.get("y") or 0) + shift

    inv_y = insight_end
    for p in body_panels:
        cfg = p.get("embeddableConfig") or {}
        content = cfg.get("content") or ""
        gd = p.get("gridData") or {}
        if "inventory" in content.lower():
            inv_y = int(gd.get("y", 0)) + int(gd.get("h", 3))
            break
    else:
        inv_y = max(
            (
                int((p.get("gridData") or {}).get("y", 0))
                + int((p.get("gridData") or {}).get("h", 0))
                for p in body_panels
            ),
            default=insight_end,
        )

    top = build_top_kpis()
    for kpi in top:
        kpi["embeddableConfig"]["hidePanelTitles"] = True

    out = (
        header_panels
        + top
        + [p for p in kept if p.get("panelIndex") == PANEL_IDS["gcp"]]
        + [summary, scoreboard, drilldowns, matrix, timeline]
        + body_panels
        + section_panels
        + rebuild_inventory_panels(inv_y)
    )
    seen: set[str] = set()
    deduped = []
    for p in out:
        pid = str(p.get("panelIndex") or uid())
        if pid in seen:
            continue
        seen.add(pid)
        deduped.append(p)
    deduped.sort(
        key=lambda p: (
            int((p.get("gridData") or {}).get("y") or 0),
            int((p.get("gridData") or {}).get("x") or 0),
            str(p.get("panelIndex") or ""),
        )
    )
    return deduped


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", type=Path, default=NDJSON)
    parser.add_argument(
        "--cps-prefix",
        action="append",
        default=None,
        help=(
            "Cross-project search alias to remove from local cockpit queries; "
            "repeat for multiple aliases (or set GCP_CPS_PREFIXES comma-separated)"
        ),
    )
    args = parser.parse_args()
    configured = args.cps_prefix
    if configured is None:
        configured = [
            value
            for value in os.environ.get("GCP_CPS_PREFIXES", "").split(",")
            if value.strip()
        ]
    prefixes = tuple(value.strip().rstrip(":") for value in configured)
    path = args.path
    lines = [l for l in path.read_text().splitlines() if l.strip()]
    objects = [json.loads(line) for line in lines]
    exported = {(obj.get("type"), obj.get("id")) for obj in objects}
    out_lines = []
    for obj in objects:
        obj["references"] = [
            reference
            for reference in obj.get("references", [])
            if (reference.get("type"), reference.get("id")) in exported
        ]
        attrs = obj.get("attributes") or {}
        if "panelsJSON" not in attrs:
            out_lines.append(json.dumps(obj, separators=(",", ":")))
            continue
        panels = json.loads(attrs["panelsJSON"])
        panels = inject(panels, prefixes)
        text = json.dumps(panels)
        assert not any(f"{prefix}:" in text for prefix in prefixes)
        assert ".alerts-security.alerts-default" not in text
        attrs["panelsJSON"] = json.dumps(panels, separators=(",", ":"))
        attrs["description"] = (
            "GCP Observe & Protect cockpit powered by three Insight Engine levels: "
            "raw GCP telemetry and discovered resources, deterministic workflow "
            "findings and recommendations, and an Agent Builder insight summary."
        )
        obj["attributes"] = attrs
        out_lines.append(json.dumps(obj, separators=(",", ":")))
        print(f"panels={len(panels)} insight panels injected into {path.name}")
    path.write_text("\n".join(out_lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
