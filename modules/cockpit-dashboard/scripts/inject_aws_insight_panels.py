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
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NDJSON = ROOT / "cockpit-aws.ndjson"

from build_aws_cockpit_ndjson import esql_metric_panel, esql_xy_panel  # noqa: E402
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


def uid() -> str:
    return str(uuid.uuid4())


def custom_panel(
    *,
    panel_id: str,
    template: str,
    esql_query: str | None,
    grid: dict,
) -> dict:
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


SCOREBOARD_TMPL = """<html>
<head>
<style>
  body { margin:0; padding: var(--cc-space-l); font-family: var(--cc-font-family); color: var(--cc-color-text); background: var(--cc-color-background); box-sizing:border-box; }
  .wrap { display:flex; flex-direction:column; gap: var(--cc-space-m); }
  .hero { display:flex; justify-content:space-between; gap: var(--cc-space-l); align-items:center; padding: var(--cc-space-m) var(--cc-space-xl); border-radius: var(--cc-radius); background: linear-gradient(135deg,#0b1f3a 0%,#16324f 55%,#1e3a5f 100%); color:#fff; box-shadow:0 2px 12px rgba(0,0,0,.18); }
  .kicker { font-size:.6875rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:#48EFCF; }
  .title { font-size:1.125rem; font-weight:600; }
  .sub { font-size:.8125rem; color:rgba(255,255,255,.78); }
  .grid { display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: var(--cc-space-m); }
  .card { background: var(--cc-color-surface); border:1px solid var(--cc-color-border); border-radius: var(--cc-radius); padding: var(--cc-space-m); box-shadow:0 1px 2px rgba(0,0,0,.04); }
  .card .label { font-size:.75rem; font-weight:700; letter-spacing:.04em; text-transform:uppercase; opacity:.7; }
  .card .value { font-size:1.75rem; font-weight:700; margin-top: var(--cc-space-xs); color:#0B64DD; }
  .card .hint { font-size:.75rem; opacity:.65; margin-top: var(--cc-space-xs); }
  .sev-high .value { color:#FF957D; }
  .sev-ok .value { color:#209280; }
  @media (max-width:900px){ .grid{ grid-template-columns:1fr 1fr; } .hero{ flex-direction:column; align-items:flex-start; } }
</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <div>
      <div class="kicker">Insight fabric</div>
      <div class="title">AWS posture at a glance</div>
      <div class="sub">Security KPIs mirrored from the Security project · coverage &amp; recommendations computed by workflows</div>
    </div>
  </div>
  <div class="grid">
    {% assign row = rows[0] %}
    <div class="card sev-high">
      <div class="label">Active alerts</div>
      <div class="value">{{ row["active_alerts"].value | default: 0 }}</div>
      <div class="hint">From Security detection engine</div>
    </div>
    <div class="card sev-high">
      <div class="label">High / critical</div>
      <div class="value">{{ row["high_critical_alerts"].value | default: 0 }}</div>
      <div class="hint">Prioritize these first</div>
    </div>
    <div class="card">
      <div class="label">CloudTrail (24h)</div>
      <div class="value">{{ row["cloudtrail_24h"].value | default: 0 }}</div>
      <div class="hint">Management API volume</div>
    </div>
    <div class="card sev-ok">
      <div class="label">AWS Health events</div>
      <div class="value">{{ row["health_events"].value | default: 0 }}</div>
      <div class="hint">Open / tracked Health items</div>
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
    <div class="title">AWS service coverage</div>
    <div class="sub">Healthy = telemetry in last window · comparable to Datadog AWS Overview tiles</div>
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
  <div class="sub">AWS Health · CloudTrail highlights · recommendation churn</div>
  <div class="list">
    {% if rows.size == 0 %}
      <div class="empty">No insight events yet — run seed_aws_insight_indices.py / wait for the next workflow cycle.</div>
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
        template=MATRIX_TMPL,
        esql_query=(
            "FROM aws-cockpit-coverage\n"
            '| WHERE category IN ("compute", "storage", "cost", "network", "platform", "security", "data")\n'
            "| SORT category ASC, label ASC\n"
            "| LIMIT 20"
        ),
        grid={"x": 0, "y": insight_y + scoreboard_h, "w": 28, "h": matrix_h},
    )
    timeline = custom_panel(
        panel_id=TIMELINE_ID,
        template=TIMELINE_TMPL,
        esql_query="FROM aws-cockpit-events\n| SORT @timestamp DESC\n| LIMIT 12",
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

    for p in body_panels:
        cfg = p.get("embeddableConfig") or {}
        content = cfg.get("content") or ""
        if "AWS inventory" in content or "### AWS inventory" in content:
            cfg["content"] = (
                "### AWS inventory (live metrics assets)\n"
                "Charts below query `aws-cockpit-assets`, refreshed by the "
                "**AWS Cockpit Asset Inventory** workflow and the insight seeder. "
                "This stays populated even when CSPM findings are empty.\n"
            )

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
