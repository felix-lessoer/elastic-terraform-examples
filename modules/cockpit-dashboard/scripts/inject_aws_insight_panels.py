#!/usr/bin/env python3
"""Inject Datadog-comparable insight panels into cockpit-aws.ndjson.

- Top KPIs read aws-cockpit-security-kpi (seeded from Security project)
- custom_content scoreboard / coverage matrix / events timeline (ES|QL + Liquid)
- Inventory charts query aws-cockpit-assets
- Scrub any remaining broken CPS qualifiers / alerts indices
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NDJSON = ROOT / "cockpit-aws.ndjson"

from build_aws_cockpit_ndjson import esql_metric_panel, esql_xy_panel  # noqa: E402
from insight_fabric_common import (  # noqa: E402
    MATRIX_TMPL,
    TIMELINE_TMPL,
    custom_panel,
    scoreboard_template,
    uid,
)
from ootb_nav import PANEL_IDS, NAV_HEIGHT, inject_ootb_nav  # noqa: E402

SCOREBOARD_ID = "c0ffee10-26e4-49d8-a2b4-548306880910"
MATRIX_ID = "c0ffee11-26e4-49d8-a2b4-548306880911"
TIMELINE_ID = "c0ffee12-26e4-49d8-a2b4-548306880912"

TOP_KPI_IDS = {
    "1dfcd0c5-db92-46ee-a0cc-6b38079265ab",
    "99c28cc1-a686-482b-9fc9-2cf7869b7b5b",
    "d170a127-afff-4154-b6c3-24a85a931382",
    "143696f7-f91e-41b2-9650-40b28c80a105",
}

AWS_SCOREBOARD_CARDS = [
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
        "label": "CloudTrail failures (24h)",
        "field": "cloudtrail_failures_24h",
        "hint": "Open failed API activity →",
        "href": 'https://aws-observe-and-protect-ad5bcf.kb.eu-west-1.aws.elastic.cloud/app/discover#/?_a=(dataSource:(type:esql),query:(esql:\'FROM logs-aws.cloudtrail* | WHERE @timestamp > NOW() - 24 hours AND event.outcome == "failure" | KEEP @timestamp, event.action, event.provider, user.name, source.ip, aws.cloudtrail.error_code, aws.cloudtrail.error_message, cloud.region | SORT @timestamp DESC | LIMIT 100\'))',
        "sev": "sev-high",
    },
    {
        "label": "AWS Health events",
        "field": "health_events",
        "hint": "Open AWS Health dashboard →",
        "href": 'https://aws-observe-and-protect-ad5bcf.kb.eu-west-1.aws.elastic.cloud/app/dashboards#/view/aws-9574244b-b538-4cc1-9666-8aac4ecf433e',
        "sev": "sev-ok",
    },
]

SCOREBOARD_TMPL = scoreboard_template(
    "AWS",
    "Security KPIs mirrored from the Security project · coverage &amp; recommendations computed by workflows",
    cards=AWS_SCOREBOARD_CARDS,
)


def build_top_kpis() -> list[dict]:
    return [
        esql_metric_panel(
            title="",
            metric_label="Security Alerts (Active)",
            esql=(
                "FROM aws-cockpit-security-kpi\n"
                "| SORT @timestamp DESC\n"
                "| LIMIT 1\n"
                "| STATS `Security Alerts (Active)` = MAX(active_alerts)"
            ),
            index="aws-cockpit-security-kpi",
            grid={"x": 0, "y": 4, "w": 12, "h": 4},
            panel_id="1dfcd0c5-db92-46ee-a0cc-6b38079265ab",
        ),
        esql_metric_panel(
            title="",
            metric_label="High/Critical Alerts",
            esql=(
                "FROM aws-cockpit-security-kpi\n"
                "| SORT @timestamp DESC\n"
                "| LIMIT 1\n"
                "| STATS `High/Critical Alerts` = MAX(high_critical_alerts)"
            ),
            index="aws-cockpit-security-kpi",
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
                "FROM aws-cockpit-security-kpi\n"
                "| SORT @timestamp DESC\n"
                "| LIMIT 1\n"
                "| STATS `CSPM findings` = MAX(cspm_findings)"
            ),
            index="aws-cockpit-security-kpi",
            grid={"x": 36, "y": 4, "w": 12, "h": 4},
            panel_id="143696f7-f91e-41b2-9650-40b28c80a105",
        ),
    ]


def scrub(panel: dict) -> dict:
    raw = json.dumps(panel)
    raw = raw.replace(
        "aws-observe-and-protect-ad5bcf:security_solution-cloud_security_posture.misconfiguration_latest",
        "security_solution-*.misconfiguration_latest",
    )
    raw = raw.replace(
        ".ml-anomalies-shared-000001,aws-observe-and-protect-ad5bcf:.ml-anomalies-shared-000001",
        ".ml-anomalies-shared-000001",
    )
    # Health lives in Security — panels must query the mirrored OBS index.
    raw = raw.replace(
        "aws-observe-and-protect-ad5bcf:metrics-aws.awshealth-default",
        "aws-cockpit-health",
    )
    raw = raw.replace("metrics-aws.awshealth-default", "aws-cockpit-health")
    raw = raw.replace("metrics-aws.awshealth*", "aws-cockpit-health")
    # Prefer assets index for inventory charts when they still point at CSPM
    return json.loads(raw)


def rebuild_inventory_panels(y: int) -> list[dict]:
    return [
        esql_xy_panel(
            title="Assets by type",
            x_field="Resource Type",
            y_field="Count",
            esql=(
                "FROM aws-cockpit-assets\n"
                "| STATS `Count` = COUNT(*) BY `Resource Type` = resource.type\n"
                "| SORT `Count` DESC\n"
                "| LIMIT 15"
            ),
            index="aws-cockpit-assets",
            grid={"x": 0, "y": y, "w": 16, "h": 14},
        ),
        esql_xy_panel(
            title="Top assets by name",
            x_field="Resource Name",
            y_field="Count",
            esql=(
                "FROM aws-cockpit-assets\n"
                "| STATS `Count` = COUNT(*) BY `Resource Name` = resource.name\n"
                "| SORT `Count` DESC\n"
                "| LIMIT 15"
            ),
            index="aws-cockpit-assets",
            grid={"x": 16, "y": y, "w": 16, "h": 14},
        ),
        esql_xy_panel(
            title="EC2 by region",
            x_field="Region",
            y_field="Instances",
            esql=(
                "FROM aws-cockpit-assets\n"
                '| WHERE resource.type == "ec2_instance"\n'
                "| STATS `Instances` = COUNT(*) BY `Region` = cloud.region\n"
                "| SORT `Instances` DESC\n"
                "| LIMIT 15"
            ),
            index="aws-cockpit-assets",
            grid={"x": 32, "y": y, "w": 16, "h": 14},
        ),
    ]


def inject(panels: list[dict]) -> list[dict]:
    drop_ids = set(TOP_KPI_IDS) | {
        SCOREBOARD_ID,
        MATRIX_ID,
        TIMELINE_ID,
        PANEL_IDS["aws"],
    }
    drop_titles = {
        "Assets by type",
        "Top assets by name",
        "Findings by evaluation",
        "EC2 by region",
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
        if p.get("type") == "markdown" and "Security Alerts" in (
            (p.get("embeddableConfig") or {}).get("content") or ""
        ):
            continue
        kept.append(scrub(p))

    # Ensure OOTB nav present / positioned at y=8
    kept = inject_ootb_nav(kept, "aws", y=8)

    insight_y = 8 + NAV_HEIGHT  # 20
    scoreboard_h, matrix_h = 8, 14
    insight_end = insight_y + scoreboard_h + matrix_h  # 42

    scoreboard = custom_panel(
        panel_id=SCOREBOARD_ID,
        template=SCOREBOARD_TMPL,
        esql_query="FROM aws-cockpit-security-kpi\n| SORT @timestamp DESC\n| LIMIT 1",
        grid={"x": 0, "y": insight_y, "w": 48, "h": scoreboard_h},
    )
    matrix = custom_panel(
        panel_id=MATRIX_ID,
        template=MATRIX_TMPL.replace(
            "Service coverage",
            "AWS service coverage",
            1,
        ),
        esql_query=(
            "FROM aws-cockpit-coverage\n"
            '| WHERE category IN ("compute", "storage", "cost", "network", "platform", "security", "data")\n'
            "| SORT category ASC, label ASC\n"
            "| LIMIT 20"
        ),
        grid={"x": 0, "y": insight_y + scoreboard_h, "w": 28, "h": matrix_h},
    )
    # Prefer actionable events: recommendations + failures + open health
    timeline = custom_panel(
        panel_id=TIMELINE_ID,
        template=TIMELINE_TMPL,
        esql_query=(
            "FROM aws-cockpit-events\n"
            '| WHERE event.source IN ("cockpit.recommendations", "aws.cloudtrail", "aws.health")\n'
            "| SORT @timestamp DESC\n"
            "| LIMIT 12"
        ),
        grid={"x": 28, "y": insight_y + scoreboard_h, "w": 20, "h": matrix_h},
    )

    # Idempotent re-pack: pin chrome panels, reflow the rest below insight_end.
    chrome_ids = {PANEL_IDS["aws"]} | TOP_KPI_IDS
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
        and p.get("panelIndex") != PANEL_IDS["aws"]
    ]

    inventory_md = (
        "### AWS inventory (live metrics assets)\n"
        "Charts below query `aws-cockpit-assets`, refreshed by the "
        "**AWS Cockpit Asset Inventory** workflow and the insight seeder. "
        "This stays populated even when CSPM findings are empty.\n"
    )
    for p in body_panels + section_panels:
        cfg = p.get("embeddableConfig") or {}
        content = cfg.get("content") or ""
        if "AWS inventory" in content or "### AWS inventory" in content:
            cfg["content"] = inventory_md

    # Preserve relative order of body panels; park them after insight block.
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
        if "AWS inventory" in content:
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
        + [p for p in kept if p.get("panelIndex") == PANEL_IDS["aws"]]
        + [scoreboard, matrix, timeline]
        + body_panels
        + section_panels
        + rebuild_inventory_panels(inv_y)
    )
    # De-dupe by panelIndex (header may already include nav)
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
        # Final scrub
        text = json.dumps(panels)
        assert "aws-observe-and-protect-ad5bcf:" not in text
        assert ".alerts-security.alerts-default" not in text
        assert "metrics-aws.awshealth" not in text
        attrs["panelsJSON"] = json.dumps(panels, separators=(",", ":"))
        # Prefer description calling out insight fabric
        attrs["description"] = (
            "AWS Observe & Protect cockpit with Datadog-comparable insight fabric: "
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
