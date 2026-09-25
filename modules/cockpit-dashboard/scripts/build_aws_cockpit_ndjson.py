#!/usr/bin/env python3
"""Build cockpit-aws.ndjson from the live GCP cockpit concept.

Takes a GCP dashboard NDJSON export (fcf1246c…) and produces an AWS cockpit
with:
  - CSPM asset inventory on misconfiguration_latest (CPS alias)
  - Live AWS resource inventory from metrics
  - Recommendations section over aws-cockpit-recommendations
"""

from __future__ import annotations

import copy
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GCP = Path("/tmp/cockpit-compare/gcp-live.ndjson")
OUT = ROOT / "cockpit-aws.ndjson"

AWS_DASH_ID = "a1b2c3d4-e5f6-4789-a012-3456789abcde"
# Elastic CPS remote: {project_alias}-{first 6 of project id}
AWS_CPS = "aws-observe-and-protect-ad5bcf"
MISCONFIG = f"{AWS_CPS}:security_solution-cloud_security_posture.misconfiguration_latest"


def uid() -> str:
    return str(uuid.uuid4())


def esql_metric_panel(
    *,
    title: str,
    esql: str,
    index: str,
    grid: dict,
    panel_id: str | None = None,
    section_id: str | None = None,
    metric_label: str | None = None,
) -> dict:
    pid = panel_id or uid()
    layer = "layer_0"
    col = "metric_accessor_metric"
    label = metric_label or title
    grid_data = dict(grid)
    grid_data["i"] = pid
    if section_id:
        grid_data["sectionId"] = section_id
    return {
        "type": "vis",
        "panelIndex": pid,
        "gridData": grid_data,
        "embeddableConfig": {
            "title": title,
            "enhancements": {},
            "attributes": {
                "title": title,
                "visualizationType": "lnsMetric",
                "version": 2,
                "state": {
                    "datasourceStates": {
                        "textBased": {
                            "layers": {
                                layer: {
                                    "index": index,
                                    "query": {"esql": esql},
                                    "timeField": "@timestamp",
                                    "columns": [
                                        {
                                            "columnId": col,
                                            "fieldName": label,
                                            "meta": {"type": "number"},
                                        }
                                    ],
                                    "ignoreGlobalFilters": False,
                                }
                            }
                        }
                    },
                    "internalReferences": [
                        {
                            "type": "index-pattern",
                            "id": index,
                            "name": f"indexpattern-datasource-layer-{layer}",
                        }
                    ],
                    "visualization": {
                        "layerId": layer,
                        "layerType": "data",
                        "metricAccessor": col,
                        "showBar": False,
                        "density": "default",
                    },
                    "query": {"query": "", "language": "kuery"},
                    "filters": [],
                },
                "references": [],
            },
        },
    }


def esql_xy_panel(
    *,
    title: str,
    esql: str,
    index: str,
    x_field: str,
    y_field: str,
    grid: dict,
    panel_id: str | None = None,
    section_id: str | None = None,
    series_type: str = "bar_horizontal",
) -> dict:
    pid = panel_id or uid()
    layer = "bar_horizontal_0"
    x_col = f"{layer}_x"
    y_col = f"{layer}_y_0"
    grid_data = dict(grid)
    grid_data["i"] = pid
    if section_id:
        grid_data["sectionId"] = section_id
    return {
        "type": "vis",
        "panelIndex": pid,
        "gridData": grid_data,
        "embeddableConfig": {
            "title": title,
            "enhancements": {},
            "attributes": {
                "title": title,
                "visualizationType": "lnsXY",
                "version": 2,
                "state": {
                    "datasourceStates": {
                        "textBased": {
                            "layers": {
                                layer: {
                                    "index": index,
                                    "query": {"esql": esql},
                                    "timeField": "@timestamp",
                                    "columns": [
                                        {
                                            "columnId": x_col,
                                            "fieldName": x_field,
                                            "meta": {"type": "string"},
                                        },
                                        {
                                            "columnId": y_col,
                                            "fieldName": y_field,
                                            "meta": {"type": "number"},
                                        },
                                    ],
                                    "ignoreGlobalFilters": False,
                                }
                            }
                        }
                    },
                    "internalReferences": [
                        {
                            "type": "index-pattern",
                            "id": index,
                            "name": f"indexpattern-datasource-layer-{layer}",
                        }
                    ],
                    "visualization": {
                        "preferredSeriesType": series_type,
                        "legend": {
                            "isVisible": True,
                            "position": "bottom",
                            "layout": "list",
                        },
                        "yLeftScale": "linear",
                        "axisTitlesVisibilitySettings": {
                            "x": False,
                            "yLeft": False,
                            "yRight": True,
                        },
                        "valueLabels": "show",
                        "layers": [
                            {
                                "layerId": layer,
                                "accessors": [y_col],
                                "layerType": "data",
                                "seriesType": series_type,
                                "xAccessor": x_col,
                                "yConfig": [{"forAccessor": y_col, "color": "#0B64DD"}],
                            }
                        ],
                    },
                    "query": {"query": "", "language": "kuery"},
                    "filters": [],
                },
                "references": [],
            },
        },
    }


def esql_table_panel(
    *,
    title: str,
    esql: str,
    index: str,
    columns: list[tuple[str, str]],
    grid: dict,
    panel_id: str | None = None,
    section_id: str | None = None,
) -> dict:
    """columns: list of (fieldName, meta_type)."""
    pid = panel_id or uid()
    layer = "table_0"
    grid_data = dict(grid)
    grid_data["i"] = pid
    if section_id:
        grid_data["sectionId"] = section_id
    col_defs = []
    for i, (fname, mtype) in enumerate(columns):
        col_defs.append(
            {
                "columnId": f"{layer}_{i}",
                "fieldName": fname,
                "meta": {"type": mtype},
            }
        )
    return {
        "type": "vis",
        "panelIndex": pid,
        "gridData": grid_data,
        "embeddableConfig": {
            "title": title,
            "enhancements": {},
            "attributes": {
                "title": title,
                "visualizationType": "lnsDatatable",
                "version": 2,
                "state": {
                    "datasourceStates": {
                        "textBased": {
                            "layers": {
                                layer: {
                                    "index": index,
                                    "query": {"esql": esql},
                                    "timeField": "@timestamp",
                                    "columns": col_defs,
                                    "ignoreGlobalFilters": False,
                                }
                            }
                        }
                    },
                    "internalReferences": [
                        {
                            "type": "index-pattern",
                            "id": index,
                            "name": f"indexpattern-datasource-layer-{layer}",
                        }
                    ],
                    "visualization": {
                        "layerId": layer,
                        "layerType": "data",
                        "columns": [
                            {
                                "columnId": c["columnId"],
                                "isTransposed": False,
                            }
                            for c in col_defs
                        ],
                    },
                    "query": {"query": "", "language": "kuery"},
                    "filters": [],
                },
                "references": [],
            },
        },
    }


def markdown_panel(content: str, grid: dict, title: str = "", section_id: str | None = None) -> dict:
    pid = uid()
    grid_data = dict(grid)
    grid_data["i"] = pid
    if section_id:
        grid_data["sectionId"] = section_id
    return {
        "type": "markdown",
        "panelIndex": pid,
        "gridData": grid_data,
        "embeddableConfig": {
            "title": title,
            "content": content,
            "enhancements": {},
        },
    }


def rewrite_gcp_panel_queries(panel: dict) -> dict:
    """Replace GCP-specific strings inside retained structural panels."""
    raw = json.dumps(panel)
    raw = raw.replace("GCP", "AWS").replace("gcp", "aws")
    raw = raw.replace(
        "gcp-observe-and-protect-ff5053:security_solution-cloud_security_posture.misconfiguration_latest",
        MISCONFIG,
    )
    # ML anomalies keep local+CPS pattern with AWS CPS alias
    raw = raw.replace(
        "gcp-observe-and-protect-ff5053:.ml-anomalies-shared-000001",
        f"{AWS_CPS}:.ml-anomalies-shared-000001",
    )
    return json.loads(raw)


def build(gcp_path: Path) -> dict:
    gcp = json.loads(gcp_path.read_text().splitlines()[0])
    panels_in = json.loads(gcp["attributes"]["panelsJSON"])

    # Keep the upper cockpit structure (header + KPIs + data flow + detection intel)
    # Drop GCP-only live metrics section panels (those with sectionId) and rebuild AWS ones.
    kept = []
    for p in panels_in:
        gd = p.get("gridData") or {}
        if gd.get("sectionId"):
            continue
        kept.append(rewrite_gcp_panel_queries(p))

    # Fix inventory markdown (panel that starts with ### AWS inventory / GCP inventory)
    for p in kept:
        cfg = p.get("embeddableConfig") or {}
        content = cfg.get("content") or ""
        if "### AWS inventory" in content or "### GCP inventory" in content:
            cfg["content"] = (
                "### AWS inventory (CSPM asset posture)\n"
                "Charts below query the **CPS-linked Security project** "
                f"`{MISCONFIG}` — the live CSPM misconfiguration index — "
                "not the empty `logs-cloud_security_posture.findings-*` pattern.\n\n"
                "Empty charts mean CSPM has not ingested findings yet (data gap), "
                "not a broken query. A **live resource inventory** from AWS metrics "
                "and **actionable recommendations** follow in the sections below."
            )
        if "### Elastic cockpit" in content:
            cfg["content"] = (
                "### Elastic cockpit\n"
                "**AWS Observability Cockpit** (Observability hub) · linked to "
                "**AWS Observe and Protect** via Cross-Project Search\n\n"
                "Security Fleet collects CSPM + CloudTrail / Security Hub / GuardDuty / Health. "
                "Observability Fleet collects metrics + vpcflow + Trusted Advisor. "
                "This view aggregates both.\n\n"
                '<span style="color:#48EFCF">■</span> healthy signal &nbsp;\n'
                '<span style="color:#FEC514">■</span> attention &nbsp;\n'
                '<span style="color:#FF957D">■</span> security pressure\n'
            )
        if "Explore the signals above" in content:
            cfg["content"] = (
                "**Explore the signals above:** "
                "[🔴 Security Alerts →](/app/security/alerts) &nbsp;|&nbsp; "
                "[🟡 ML Anomaly Explorer →](/app/ml/explorer) &nbsp;|&nbsp; "
                "[🔵 CSPM Misconfiguration Findings →]"
                "(/app/security/cloud_security_posture/findings/misconfigurations) &nbsp;|&nbsp; "
                "[🟢 Recommendations →](#aws-recommendations)\n\n"
                "Click a link to jump straight to the detailed investigation view for that signal type."
            )
        if "ML jobs (provisioned)" in (cfg.get("title") or "") or (
            "**aws-event-rate**" in content or "**gcp-event-rate**" in content
        ):
            if "aws-event-rate" in content or "gcp-event-rate" in content:
                cfg["content"] = (
                    "| Job | Purpose | State |\n"
                    "| --- | --- | --- |\n"
                    "| **aws-event-rate** | Unusual drops/spikes in AWS telemetry volume | Configured (lazy open) |\n"
                    "| **aws-cspm-findings-rate** | Unusual rate of CSPM findings documents | Configured (lazy open) |\n"
                )
                cfg["title"] = "ML jobs (provisioned)"
        if "AI agents (provisioned)" in (cfg.get("title") or "") or "aws-security-analyst" in content or "gcp-security-analyst" in content:
            if "security-analyst" in content:
                cfg["content"] = (
                    "| Agent | Role | State |\n"
                    "| --- | --- | --- |\n"
                    "| **aws-security-analyst** | Triage CSPM + detection alerts across CPS | Ready in Agent Builder |\n"
                    "| **aws-obs-triage** | Explain telemetry gaps and alert bursts | Ready in Agent Builder |\n\n"
                    "Open **Agent Builder** in this Observability project to chat with them.\n"
                )
                cfg["title"] = "AI agents (provisioned)"

    # Drop legacy findings-* panels and any prior CSPM inventory / KPI panels —
    # we rebuild those explicitly below against misconfiguration_latest.
    for p in kept:
        title = (p.get("embeddableConfig") or {}).get("title") or ""
        attrs = (p.get("embeddableConfig") or {}).get("attributes") or {}
        atitle = attrs.get("title") or title
        content = (p.get("embeddableConfig") or {}).get("content") or ""
        raw = json.dumps(p)
        drop_titles = {
            "CSPM findings (24h)",
            "Assets by type",
            "Top assets by name",
            "Findings by evaluation",
            "AWS inventory",
            "GCP inventory",
        }
        if (
            atitle in drop_titles
            or title in drop_titles
            or "### AWS inventory" in content
            or "### GCP inventory" in content
            or "misconfiguration_latest" in raw
            or "logs-cloud_security_posture.findings" in raw
        ):
            p["_drop"] = True

    kept = [p for p in kept if not p.get("_drop")]

    # Re-add fixed CSPM KPI (top row right) and inventory charts
    # Find max y among kept non-section panels to place inventory after ML
    max_y = 0
    for p in kept:
        gd = p.get("gridData") or {}
        max_y = max(max_y, int(gd.get("y", 0)) + int(gd.get("h", 0)))

    # Top-row CSPM KPI at y=6 x=36 (GCP layout)
    cspm_kpi = esql_metric_panel(
        title="CSPM findings (24h)",
        metric_label="CSPM findings (24h)",
        esql=(
            f"FROM {MISCONFIG}\n"
            "| WHERE @timestamp >= ?_tstart AND @timestamp < ?_tend\n"
            "| STATS `CSPM findings (24h)` = COUNT(*)"
        ),
        index=f"{MISCONFIG}-@timestamp",
        grid={"x": 36, "y": 6, "w": 12, "h": 8},
    )

    inv_header = markdown_panel(
        title="AWS inventory",
        content=(
            "### AWS inventory (CSPM asset posture)\n"
            "Charts below query the **CPS-linked Security project** "
            f"`{MISCONFIG}` via cross-project search.\n\n"
            "A **live resource inventory** from AWS metrics and "
            "**recommendations** derived from those metrics are in the next sections."
        ),
        grid={"x": 0, "y": max_y, "w": 48, "h": 3},
    )
    inv_y = max_y + 3
    assets_by_type = esql_xy_panel(
        title="Assets by type",
        x_field="Resource Type",
        y_field="Finding Count",
        esql=(
            f"FROM {MISCONFIG}\n"
            "| WHERE @timestamp >= ?_tstart AND @timestamp < ?_tend\n"
            "| STATS `Finding Count` = COUNT(*) BY `Resource Type` = resource.type\n"
            "| SORT `Finding Count` DESC\n"
            "| LIMIT 15"
        ),
        index=f"{MISCONFIG}-@timestamp",
        grid={"x": 0, "y": inv_y, "w": 16, "h": 14},
    )
    top_assets = esql_xy_panel(
        title="Top assets by name",
        x_field="Resource Name",
        y_field="Count",
        esql=(
            f"FROM {MISCONFIG}\n"
            "| WHERE @timestamp >= ?_tstart AND @timestamp < ?_tend\n"
            "| STATS `Count` = COUNT(*) BY `Resource Name` = resource.name\n"
            "| SORT `Count` DESC\n"
            "| LIMIT 15"
        ),
        index=f"{MISCONFIG}-@timestamp",
        grid={"x": 16, "y": inv_y, "w": 16, "h": 14},
    )
    by_eval = esql_xy_panel(
        title="Findings by evaluation",
        x_field="Evaluation Result",
        y_field="Finding Count",
        esql=(
            f"FROM {MISCONFIG}\n"
            "| STATS `Finding Count` = COUNT(*) BY `Evaluation Result` = result.evaluation\n"
            "| SORT `Finding Count` DESC\n"
            "| LIMIT 10"
        ),
        index=f"{MISCONFIG}-@timestamp",
        grid={"x": 32, "y": inv_y, "w": 16, "h": 14},
    )

    # Section: live metrics inventory
    live_section_id = uid()
    live_section_y = inv_y + 14

    # Section: recommendations
    rec_section_id = uid()
    rec_section_y = live_section_y + 52  # approximate; sections use relative y

    live_intro = markdown_panel(
        title="",
        section_id=live_section_id,
        content=(
            "### How to explore a resource further\n"
            "Use the filter controls pinned above (EC2 instance, S3 bucket, billing service) "
            "to scope panels on this page. Then:\n\n"
            "| Resource kind | Where to dig deeper |\n"
            "| --- | --- |\n"
            "| **EC2 instance** | Filter by instance name; check CPU / status below, or Discover on "
            "`metrics-aws.ec2_metrics-*` / `logs-*` filtered to `cloud.instance.name`. |\n"
            "| **S3 bucket** | Filter by bucket; size table below shows stored bytes. Cross-check "
            "CSPM findings (once populated) for misconfigurations. |\n"
                            "| **Billing service** | Top estimated charges by service — often only populated from "
                            "**us-east-1** even when `aws_regions` lists more. Empty other regions are expected. |\n"
                            "| **Trusted Advisor / Health** | Same home-region pattern — panels stay valid when only "
                            "one region in `aws_regions` has data. |\n\n"
                            "Metrics are collected across every region in Terraform `aws_regions`; charts aggregate "
                            "whatever `cloud.region` values exist (no region is required to have data). "
                            "All figures reflect the dashboard's selected time range."
        ),
        grid={"x": 0, "y": 0, "w": 48, "h": 7},
    )

    ec2_idx = "metrics-aws.ec2_metrics-default"
    s3_idx = "metrics-aws.s3_daily_storage-default"
    bill_idx = "metrics-aws.billing-default"

    live_kpis = [
        esql_metric_panel(
            title="EC2 instances",
            metric_label="Unique Instances",
            esql=(
                f"FROM {ec2_idx}\n"
                "| WHERE @timestamp >= ?_tstart AND @timestamp < ?_tend\n"
                "| STATS `Unique Instances` = COUNT_DISTINCT(COALESCE(cloud.instance.name, cloud.instance.id))"
            ),
            index=f"{ec2_idx}-@timestamp",
            grid={"x": 0, "y": 7, "w": 8, "h": 5},
            section_id=live_section_id,
        ),
        esql_metric_panel(
            title="Availability zones",
            metric_label="AZ Count",
            esql=(
                f"FROM {ec2_idx}\n"
                "| WHERE @timestamp >= ?_tstart AND @timestamp < ?_tend\n"
                "| STATS `AZ Count` = COUNT_DISTINCT(cloud.availability_zone)"
            ),
            index=f"{ec2_idx}-@timestamp",
            grid={"x": 8, "y": 7, "w": 8, "h": 5},
            section_id=live_section_id,
        ),
        esql_metric_panel(
            title="S3 buckets",
            metric_label="Unique Buckets",
            esql=(
                f"FROM {s3_idx}\n"
                "| WHERE @timestamp >= ?_tstart AND @timestamp < ?_tend\n"
                "| STATS `Unique Buckets` = COUNT_DISTINCT(`aws.s3.bucket.name`)"
            ),
            index=f"{s3_idx}-@timestamp",
            grid={"x": 16, "y": 7, "w": 8, "h": 5},
            section_id=live_section_id,
        ),
        esql_metric_panel(
            title="Billing services",
            metric_label="Service Count",
            esql=(
                f"FROM {bill_idx}\n"
                "| WHERE @timestamp >= ?_tstart AND @timestamp < ?_tend\n"
                "| STATS `Service Count` = COUNT_DISTINCT(`aws.billing.ServiceName`)"
            ),
            index=f"{bill_idx}-@timestamp",
            grid={"x": 24, "y": 7, "w": 8, "h": 5},
            section_id=live_section_id,
        ),
        esql_metric_panel(
            title="Open recommendations",
            metric_label="Recommendations",
            esql=(
                "FROM aws-cockpit-recommendations\n"
                "| WHERE @timestamp >= ?_tstart AND @timestamp < ?_tend\n"
                "| STATS `Recommendations` = COUNT(*)"
            ),
            index="aws-cockpit-recommendations-@timestamp",
            grid={"x": 32, "y": 7, "w": 8, "h": 5},
            section_id=live_section_id,
        ),
        esql_metric_panel(
            title="High severity recs",
            metric_label="High severity",
            esql=(
                "FROM aws-cockpit-recommendations\n"
                '| WHERE @timestamp >= ?_tstart AND @timestamp < ?_tend AND severity == "high"\n'
                "| STATS `High severity` = COUNT(*)"
            ),
            index="aws-cockpit-recommendations-@timestamp",
            grid={"x": 40, "y": 7, "w": 8, "h": 5},
            section_id=live_section_id,
        ),
    ]

    live_charts = [
        esql_xy_panel(
            title="Distinct Instance Count by Availability Zone",
            x_field="Availability Zone",
            y_field="Instance Count",
            esql=(
                f"FROM {ec2_idx}\n"
                "| WHERE @timestamp >= ?_tstart AND @timestamp < ?_tend\n"
                "| STATS `Instance Count` = COUNT_DISTINCT(COALESCE(cloud.instance.name, cloud.instance.id)) "
                "BY `Availability Zone` = cloud.availability_zone\n"
                "| SORT `Instance Count` DESC\n"
                "| LIMIT 15"
            ),
            index=f"{ec2_idx}-@timestamp",
            grid={"x": 0, "y": 12, "w": 16, "h": 10},
            section_id=live_section_id,
        ),
        esql_xy_panel(
            title="Resources observed by region",
            x_field="Region",
            y_field="Instances",
            esql=(
                f"FROM {ec2_idx}\n"
                "| WHERE @timestamp >= ?_tstart AND @timestamp < ?_tend\n"
                "| STATS `Instances` = COUNT_DISTINCT(COALESCE(cloud.instance.name, cloud.instance.id)) "
                "BY `Region` = cloud.region\n"
                "| SORT `Instances` DESC\n"
                "| LIMIT 15"
            ),
            index=f"{ec2_idx}-@timestamp",
            grid={"x": 16, "y": 12, "w": 16, "h": 10},
            section_id=live_section_id,
        ),
        esql_xy_panel(
            title="Estimated Charges by Service (Top 15)",
            x_field="Service",
            y_field="Estimated Charges",
            esql=(
                f"FROM {bill_idx}\n"
                "| WHERE @timestamp >= ?_tstart AND @timestamp < ?_tend\n"
                "| STATS `Estimated Charges` = MAX(`aws.billing.EstimatedCharges`) "
                "BY `Service` = `aws.billing.ServiceName`\n"
                "| SORT `Estimated Charges` DESC\n"
                "| LIMIT 15"
            ),
            index=f"{bill_idx}-@timestamp",
            grid={"x": 32, "y": 12, "w": 16, "h": 10},
            section_id=live_section_id,
        ),
        esql_table_panel(
            title="S3 Bucket Size by Bucket and Region",
            esql=(
                f"FROM {s3_idx}\n"
                "| WHERE @timestamp >= ?_tstart AND @timestamp < ?_tend\n"
                "| STATS `bytes` = MAX(`aws.s3_daily_storage.bucket.size.bytes`), "
                "`objects` = MAX(`aws.s3_daily_storage.number_of_objects`) "
                "BY `bucket` = `aws.s3.bucket.name`, `region` = cloud.region\n"
                "| SORT `bytes` DESC\n"
                "| LIMIT 50"
            ),
            index=f"{s3_idx}-@timestamp",
            columns=[
                ("bucket", "string"),
                ("region", "string"),
                ("bytes", "number"),
                ("objects", "number"),
            ],
            grid={"x": 0, "y": 22, "w": 48, "h": 14},
            section_id=live_section_id,
        ),
        esql_table_panel(
            title="Average CPU Utilization by EC2 Instance",
            esql=(
                f"FROM {ec2_idx}\n"
                "| WHERE @timestamp >= ?_tstart AND @timestamp < ?_tend\n"
                "| STATS `avg_cpu` = AVG(`aws.ec2.metrics.CPUUtilization.avg`), "
                "`max_cpu` = MAX(`aws.ec2.metrics.CPUUtilization.avg`) "
                "BY `instance` = COALESCE(cloud.instance.name, cloud.instance.id), "
                "`az` = cloud.availability_zone, `type` = cloud.machine.type\n"
                "| SORT `avg_cpu` DESC\n"
                "| LIMIT 50"
            ),
            index=f"{ec2_idx}-@timestamp",
            columns=[
                ("instance", "string"),
                ("az", "string"),
                ("type", "string"),
                ("avg_cpu", "number"),
                ("max_cpu", "number"),
            ],
            grid={"x": 0, "y": 36, "w": 48, "h": 14},
            section_id=live_section_id,
        ),
    ]

    rec_intro = markdown_panel(
        title="AWS recommendations",
        section_id=rec_section_id,
        content=(
            '<a id="aws-recommendations"></a>\n'
            "### Recommendations (from live AWS metrics)\n"
            "Derived from EC2 CPU / status checks and S3 utilization, written to "
            "`aws-cockpit-recommendations` (same concept as GCP's "
            "`gcp-cockpit-recommendations`).\n\n"
            "| Category | Meaning |\n"
            "| --- | --- |\n"
            "| **cost_optimization** | Underutilized EC2 (avg CPU &lt; 5% / 24h) or empty S3 buckets |\n"
            "| **performance_risk** | Hot EC2 (avg CPU &gt; 85%) or failed status checks |\n\n"
            "Regenerate anytime with "
            "`python3 modules/cockpit-dashboard/scripts/generate_aws_recommendations.py`."
        ),
        grid={"x": 0, "y": 0, "w": 48, "h": 6},
    )

    rec_panels = [
        rec_intro,
        esql_xy_panel(
            title="Recommendations by category",
            x_field="Category",
            y_field="Count",
            esql=(
                "FROM aws-cockpit-recommendations\n"
                "| WHERE @timestamp >= ?_tstart AND @timestamp < ?_tend\n"
                "| STATS `Count` = COUNT(*) BY `Category` = category\n"
                "| SORT `Count` DESC"
            ),
            index="aws-cockpit-recommendations-@timestamp",
            grid={"x": 0, "y": 6, "w": 16, "h": 12},
            section_id=rec_section_id,
        ),
        esql_xy_panel(
            title="Recommendations by severity",
            x_field="Severity",
            y_field="Count",
            esql=(
                "FROM aws-cockpit-recommendations\n"
                "| WHERE @timestamp >= ?_tstart AND @timestamp < ?_tend\n"
                "| STATS `Count` = COUNT(*) BY `Severity` = severity\n"
                "| SORT `Count` DESC"
            ),
            index="aws-cockpit-recommendations-@timestamp",
            grid={"x": 16, "y": 6, "w": 16, "h": 12},
            section_id=rec_section_id,
        ),
        esql_xy_panel(
            title="Recommendations by resource type",
            x_field="Resource Type",
            y_field="Count",
            esql=(
                "FROM aws-cockpit-recommendations\n"
                "| WHERE @timestamp >= ?_tstart AND @timestamp < ?_tend\n"
                "| STATS `Count` = COUNT(*) BY `Resource Type` = resource.type\n"
                "| SORT `Count` DESC"
            ),
            index="aws-cockpit-recommendations-@timestamp",
            grid={"x": 32, "y": 6, "w": 16, "h": 12},
            section_id=rec_section_id,
        ),
        esql_table_panel(
            title="Latest recommendations",
            esql=(
                "FROM aws-cockpit-recommendations\n"
                "| WHERE @timestamp >= ?_tstart AND @timestamp < ?_tend\n"
                "| KEEP @timestamp, severity, category, resource.type, resource.name, recommendation, metric_name, metric_value\n"
                "| SORT severity ASC, @timestamp DESC\n"
                "| LIMIT 50"
            ),
            index="aws-cockpit-recommendations-@timestamp",
            columns=[
                ("@timestamp", "date"),
                ("severity", "string"),
                ("category", "string"),
                ("resource.type", "string"),
                ("resource.name", "string"),
                ("recommendation", "string"),
                ("metric_name", "string"),
                ("metric_value", "number"),
            ],
            grid={"x": 0, "y": 18, "w": 48, "h": 16},
            section_id=rec_section_id,
        ),
    ]

    panels_out = kept + [cspm_kpi, inv_header, assets_by_type, top_assets, by_eval, live_intro, *live_kpis, *live_charts, *rec_panels]

    # Pinned controls (AWS equivalents of GCP filters)
    pinned = {
        "panels": {
            uid(): {
                "type": "options_list_control",
                "order": 0,
                "grow": True,
                "width": "medium",
                "config": {
                    "title": "EC2 instance",
                    "esql_query": (
                        f"FROM {ec2_idx} | STATS BY COALESCE(cloud.instance.name, cloud.instance.id)"
                    ),
                    "values_source": "esql",
                    "selected_options": [],
                    "exclude": False,
                    "exists_selected": False,
                    "single_select": False,
                    "search_technique": "wildcard",
                    "use_global_filters": True,
                    "ignore_validations": False,
                    "run_past_timeout": False,
                    "sort": {"by": "_key", "direction": "desc"},
                },
            },
            uid(): {
                "type": "options_list_control",
                "order": 1,
                "grow": True,
                "width": "medium",
                "config": {
                    "title": "S3 bucket",
                    "esql_query": f"FROM {s3_idx} | STATS BY `aws.s3.bucket.name`",
                    "values_source": "esql",
                    "selected_options": [],
                    "exclude": False,
                    "exists_selected": False,
                    "single_select": False,
                    "search_technique": "wildcard",
                    "use_global_filters": True,
                    "ignore_validations": False,
                    "run_past_timeout": False,
                    "sort": {"by": "_key", "direction": "desc"},
                },
            },
            uid(): {
                "type": "options_list_control",
                "order": 2,
                "grow": True,
                "width": "medium",
                "config": {
                    "title": "Billing service",
                    "esql_query": f"FROM {bill_idx} | STATS BY `aws.billing.ServiceName`",
                    "values_source": "esql",
                    "selected_options": [],
                    "exclude": False,
                    "exists_selected": False,
                    "single_select": False,
                    "search_technique": "wildcard",
                    "use_global_filters": True,
                    "ignore_validations": False,
                    "run_past_timeout": False,
                    "sort": {"by": "_key", "direction": "desc"},
                },
            },
        }
    }

    sections = [
        {
            "collapsed": False,
            "gridData": {"i": live_section_id, "y": live_section_y},
            "title": "AWS Resource Inventory (Live Metrics)",
        },
        {
            "collapsed": False,
            "gridData": {"i": rec_section_id, "y": live_section_y + 55},
            "title": "AWS Recommendations",
        },
    ]

    dash = {
        "attributes": {
            "description": (
                "Aggregated security + observability posture across linked Elastic serverless AWS projects. "
                "Includes CSPM asset inventory, live AWS metrics inventory, and cost/performance recommendations."
            ),
            "esqlApproximation": False,
            "kibanaSavedObjectMeta": {"searchSourceJSON": json.dumps({"query": {"query": "", "language": "kuery"}})},
            "optionsJSON": json.dumps(
                {
                    "autoApplyFilters": True,
                    "hidePanelTitles": False,
                    "hidePanelBorders": False,
                    "useMargins": True,
                    "syncColors": True,
                    "syncTooltips": True,
                    "syncCursor": True,
                }
            ),
            "panelsJSON": json.dumps(panels_out),
            "pinned_panels": pinned,
            "refreshInterval": {"pause": False, "value": 60000},
            "sections": sections,
            "timeFrom": "now-24h",
            "timeRestore": True,
            "timeTo": "now",
            "title": "AWS Observe & Protect Cockpit",
        },
        "coreMigrationVersion": "8.8.0",
        "created_at": "2026-09-25T18:00:00.000Z",
        "id": AWS_DASH_ID,
        "managed": False,
        "references": [
            {"id": "cockpit", "name": "tag-ref-cockpit", "type": "tag"},
            {"id": "aws", "name": "tag-ref-aws", "type": "tag"},
            {"id": "observe-and-protect", "name": "tag-ref-observe-and-protect", "type": "tag"},
            {"id": "cps", "name": "tag-ref-cps", "type": "tag"},
        ],
        "type": "dashboard",
        "typeMigrationVersion": "10.3.0",
        "updated_at": "2026-09-25T18:40:00.000Z",
        "version": "WzEsMV0=",
    }
    return dash


def main() -> int:
    gcp_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_GCP
    if not gcp_path.exists():
        print(f"GCP export not found: {gcp_path}", file=sys.stderr)
        return 1
    dash = build(gcp_path)
    OUT.write_text(json.dumps(dash, separators=(",", ":")) + "\n")
    panels = json.loads(dash["attributes"]["panelsJSON"])
    print(f"Wrote {OUT} with {len(panels)} panels, {len(dash['attributes']['sections'])} sections")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
