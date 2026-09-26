#!/usr/bin/env python3
"""Inject Datadog-comparable insight panels into cockpit-azure.ndjson."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NDJSON = ROOT / "cockpit-azure.ndjson"

from build_aws_cockpit_ndjson import esql_metric_panel, esql_xy_panel  # noqa: E402
from insight_fabric_common import (  # noqa: E402
    MATRIX_TMPL,
    TIMELINE_TMPL,
    custom_panel,
    scoreboard_template,
    uid,
)
from ootb_nav import NAV_HEIGHT, PANEL_IDS, inject_ootb_nav  # noqa: E402

SCOREBOARD_ID = "c0ffee10-9a7d-4e3b-8c5a-1d6f0e9b2a10"
MATRIX_ID = "c0ffee11-9a7d-4e3b-8c5a-1d6f0e9b2a11"
TIMELINE_ID = "c0ffee12-9a7d-4e3b-8c5a-1d6f0e9b2a12"

TOP_KPI_IDS = {
    "1dfcd0c5-db92-46ee-a0cc-6b38079265ab",
    "99c28cc1-a686-482b-9fc9-2cf7869b7b5b",
    "d170a127-afff-4154-b6c3-24a85a931382",
    "6c024771-3e68-4b87-86f3-229381a4f7b7",
    "143696f7-f91e-41b2-9650-40b28c80a105",
}

KPI_INDEX = "azure-cockpit-security-kpi"
ASSETS_INDEX = "azure-cockpit-assets"
CPS_PREFIXES = (
    "azure-observe-and-protect-azure0",
    "azure-observe-and-protect-",
)


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
            panel_id="6c024771-3e68-4b87-86f3-229381a4f7b7",
        ),
    ]


def scrub(panel: dict) -> dict:
    raw = json.dumps(panel)
    for prefix in CPS_PREFIXES:
        raw = raw.replace(
            f"{prefix}:security_solution-cloud_security_posture.misconfiguration_latest",
            "security_solution-*.misconfiguration_latest",
        )
        raw = raw.replace(
            f".ml-anomalies-shared-000001,{prefix}:.ml-anomalies-shared-000001",
            ".ml-anomalies-shared-000001",
        )
        # Strip any remaining CPS-qualified index strings for this alias.
        raw = raw.replace(f'"{prefix}:', '"')
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
        ),
        esql_xy_panel(
            title="VMs by region",
            x_field="Region",
            y_field="VMs",
            esql=(
                f"FROM {ASSETS_INDEX}\n"
                '| WHERE resource.type == "azure_vm"\n'
                "| STATS `VMs` = COUNT(*) BY `Region` = cloud.region\n"
                "| SORT `VMs` DESC\n"
                "| LIMIT 15"
            ),
            index=ASSETS_INDEX,
            grid={"x": 32, "y": y, "w": 16, "h": 14},
        ),
    ]


def inject(panels: list[dict]) -> list[dict]:
    drop_ids = set(TOP_KPI_IDS) | {
        SCOREBOARD_ID,
        MATRIX_ID,
        TIMELINE_ID,
        PANEL_IDS["azure"],
    }
    drop_titles = {
        "Assets by type",
        "Top assets by name",
        "Findings by evaluation",
        "VMs by region",
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
        kept.append(scrub(p))

    kept = inject_ootb_nav(kept, "azure", y=8)
    insight_y = 8 + NAV_HEIGHT
    scoreboard_h, matrix_h = 8, 14
    insight_end = insight_y + scoreboard_h + matrix_h

    scoreboard = custom_panel(
        panel_id=SCOREBOARD_ID,
        template=scoreboard_template(
            "Azure",
            "Security KPIs mirrored from the Security project · coverage & recommendations computed by workflows",
        ),
        esql_query=f"FROM {KPI_INDEX}\n| SORT @timestamp DESC\n| LIMIT 1",
        grid={"x": 0, "y": insight_y, "w": 48, "h": scoreboard_h},
    )
    matrix = custom_panel(
        panel_id=MATRIX_ID,
        template=MATRIX_TMPL,
        esql_query=(
            "FROM azure-cockpit-coverage\n"
            '| WHERE category IN ("compute", "storage", "cost", "network", "platform", "security", "data")\n'
            "| SORT category ASC, label ASC\n"
            "| LIMIT 20"
        ),
        grid={"x": 0, "y": insight_y + scoreboard_h, "w": 28, "h": matrix_h},
    )
    timeline = custom_panel(
        panel_id=TIMELINE_ID,
        template=TIMELINE_TMPL,
        esql_query="FROM azure-cockpit-events\n| SORT @timestamp DESC\n| LIMIT 12",
        grid={"x": 28, "y": insight_y + scoreboard_h, "w": 20, "h": matrix_h},
    )

    chrome_ids = {PANEL_IDS["azure"]} | TOP_KPI_IDS
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
        and p.get("panelIndex") != PANEL_IDS["azure"]
    ]

    inventory_md = (
        "### Azure inventory (live metrics assets)\n"
        "Charts below query `azure-cockpit-assets`, refreshed by the "
        "**Azure Cockpit Asset Inventory** workflow and the insight seeder.\n"
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
        + [p for p in kept if p.get("panelIndex") == PANEL_IDS["azure"]]
        + [scoreboard, matrix, timeline]
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
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else NDJSON
    lines = [l for l in path.read_text().splitlines() if l.strip()]
    out_lines = []
    for line in lines:
        obj = json.loads(line)
        attrs = obj.get("attributes") or {}
        if "panelsJSON" not in attrs:
            out_lines.append(json.dumps(obj, separators=(",", ":")))
            continue
        panels = json.loads(attrs["panelsJSON"])
        panels = inject(panels)
        text = json.dumps(panels)
        assert "azure-observe-and-protect-azure0:" not in text
        assert ".alerts-security.alerts-default" not in text
        attrs["panelsJSON"] = json.dumps(panels, separators=(",", ":"))
        attrs["description"] = (
            "Azure Observe & Protect cockpit with Datadog-comparable insight fabric: "
            "mirrored Security KPIs, service coverage matrix, events timeline, "
            "live asset inventory, OOTB integration nav, and recommendation workflows."
        )
        obj["attributes"] = attrs
        out_lines.append(json.dumps(obj, separators=(",", ":")))
        print(f"panels={len(panels)} insight panels injected into {path.name}")
    path.write_text("\n".join(out_lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
