#!/usr/bin/env python3
"""Markdown drill-down panels for insight fabric.

Kibana ``custom_content`` strips ``<a>`` tags and sandboxes iframes with
``default-src 'none'``, so aggregates rendered there cannot navigate.
Markdown panels *do* allow links — use these beside the fabric visuals.
"""

from __future__ import annotations

from insight_fabric_common import discover_esql_href, recommendation_discover_href

# Stable panel ids (idempotent re-inject).
DRILLDOWN_IDS = {
    "aws": "c0ffee1d-26e4-49d8-a2b4-54830688091d",
    "gcp": "c0ffee1d-6ee2-4c91-94f8-f034e8d3451d",
    "azure": "c0ffee1d-9a7d-4e3b-8c5a-1d6f0e9b2a1d",
}

SEC_KIBANA = {
    "aws": "https://aws-observe-and-protect-ad5bcf.kb.eu-west-1.aws.elastic.cloud",
    "gcp": "",  # filled when known; relative links used as fallback
    "azure": "",
}

AWS_COVERAGE_LINKS = [
    ("EC2", "/app/dashboards#/view/aws-c5846400-f7fb-11e8-af03-c999c9dea608"),
    ("S3", "/app/dashboards#/view/aws-a096b830-4762-11e9-8062-c98a86cb6f94"),
    ("Billing", "/app/dashboards#/view/aws-e6776b10-1534-11ea-841c-01bf20a6c8ba"),
    ("VPC Flow", "/app/dashboards#/view/aws-15503340-4488-11ea-ad63-791a5dc86f10"),
    ("CloudWatch", "/app/dashboards#/view/aws-fac28650-7349-11e9-816b-07687310a99a"),
    ("Lambda", "/app/dashboards#/view/aws-7ac8e1d0-28d2-11ea-ba6c-49a884eb104f"),
    ("RDS", "/app/dashboards#/view/aws-3367c170-921f-11e9-aa19-159bf182e06f"),
]

AWS_SEC_COVERAGE_LINKS = [
    ("CloudTrail", "/app/dashboards#/view/aws-9c09cd20-7399-11ea-a345-f985c61fe654"),
    ("AWS Health", "/app/dashboards#/view/aws-9574244b-b538-4cc1-9666-8aac4ecf433e"),
    ("GuardDuty", "/app/dashboards#/view/aws-9d21f520-6a36-11ed-b880-2f1b70138655"),
    ("Security Hub", "/app/dashboards#/view/aws-c9f103d0-5f63-11ed-bd69-473ce047ef30"),
]


def _md_link(label: str, href: str) -> str:
    return f"[{label}]({href})"


def aws_drilldowns_markdown() -> str:
    sec = SEC_KIBANA["aws"].rstrip("/")
    ct_fail = sec + discover_esql_href(
        "FROM logs-aws.cloudtrail*\n"
        '| WHERE @timestamp > NOW() - 24 hours AND event.outcome == "failure"\n'
        "| KEEP @timestamp, event.action, event.provider, user.name, source.ip, "
        "aws.cloudtrail.error_code, aws.cloudtrail.error_message, cloud.region\n"
        "| SORT @timestamp DESC\n"
        "| LIMIT 100"
    )
    cost = recommendation_discover_href(
        "aws-cockpit-recommendations", category="cost_optimization"
    )
    perf = recommendation_discover_href(
        "aws-cockpit-recommendations", category="performance_risk"
    )
    health = f"{sec}/app/dashboards#/view/aws-9574244b-b538-4cc1-9666-8aac4ecf433e"
    cov_obs = " · ".join(_md_link(lbl, href) for lbl, href in AWS_COVERAGE_LINKS)
    cov_sec = " · ".join(
        _md_link(lbl, f"{sec}{href}") for lbl, href in AWS_SEC_COVERAGE_LINKS
    )
    return "\n".join(
        [
            "### Drill down from the insight fabric",
            "Custom content panels cannot host links (Kibana strips them) — use these jumps:",
            "",
            "**Scoreboard** · "
            + " · ".join(
                [
                    _md_link("Active alerts →", "/app/security/alerts"),
                    _md_link("High / critical →", "/app/security/alerts"),
                    _md_link("CloudTrail failures →", ct_fail),
                    _md_link("AWS Health →", health),
                ]
            ),
            "",
            "**Recommendations** · "
            + " · ".join(
                [
                    _md_link("Cost optimization details →", cost),
                    _md_link("Performance risk details →", perf),
                    _md_link(
                        "All recommendations →",
                        recommendation_discover_href("aws-cockpit-recommendations"),
                    ),
                ]
            ),
            "",
            f"**Coverage (Observability)** · {cov_obs}",
            "",
            f"**Coverage (Security)** · {cov_sec}",
            "",
        ]
    )


def gcp_drilldowns_markdown() -> str:
    cost = recommendation_discover_href(
        "gcp-cockpit-recommendations", category="cost_optimization"
    )
    return "\n".join(
        [
            "### Drill down from the insight fabric",
            "Custom content panels cannot host links — use these jumps:",
            "",
            "**Scoreboard** · "
            + " · ".join(
                [
                    _md_link("Active alerts →", "/app/security/alerts"),
                    _md_link("High / critical →", "/app/security/alerts"),
                    _md_link(
                        "Audit dashboard →",
                        "/app/dashboards#/view/gcp-48e12760-cbe4-11ec-b519-85ccf621cbbf",
                    ),
                    _md_link(
                        "CSPM findings →",
                        "/app/security/cloud_security_posture/findings/misconfigurations",
                    ),
                ]
            ),
            "",
            "**Recommendations** · "
            + " · ".join(
                [
                    _md_link("Cost optimization details →", cost),
                    _md_link(
                        "All recommendations →",
                        recommendation_discover_href("gcp-cockpit-recommendations"),
                    ),
                ]
            ),
            "",
        ]
    )


def azure_drilldowns_markdown() -> str:
    cost = recommendation_discover_href(
        "azure-cockpit-recommendations", category="cost_optimization"
    )
    return "\n".join(
        [
            "### Drill down from the insight fabric",
            "Custom content panels cannot host links — use these jumps:",
            "",
            "**Scoreboard** · "
            + " · ".join(
                [
                    _md_link("Active alerts →", "/app/security/alerts"),
                    _md_link("High / critical →", "/app/security/alerts"),
                    _md_link(
                        "Activity logs →",
                        "/app/dashboards#/view/azure-41e84340-ec20-11e9-90ec-112a988266d5",
                    ),
                    _md_link(
                        "CSPM findings →",
                        "/app/security/cloud_security_posture/findings/misconfigurations",
                    ),
                ]
            ),
            "",
            "**Recommendations** · "
            + " · ".join(
                [
                    _md_link("Cost optimization details →", cost),
                    _md_link(
                        "All recommendations →",
                        recommendation_discover_href("azure-cockpit-recommendations"),
                    ),
                ]
            ),
            "",
        ]
    )


def drilldowns_panel(cloud: str, *, y: int, h: int = 5) -> dict:
    cloud = cloud.lower()
    content = {
        "aws": aws_drilldowns_markdown,
        "gcp": gcp_drilldowns_markdown,
        "azure": azure_drilldowns_markdown,
    }[cloud]()
    pid = DRILLDOWN_IDS[cloud]
    return {
        "type": "markdown",
        "panelIndex": pid,
        "gridData": {"x": 0, "y": y, "w": 48, "h": h, "i": pid},
        "embeddableConfig": {
            "title": "",
            "hidePanelTitles": True,
            "content": content,
            "settings": {"open_links_in_new_tab": False},
            "enhancements": {},
        },
    }
