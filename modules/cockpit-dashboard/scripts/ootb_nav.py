#!/usr/bin/env python3
"""Shared OOTB integration dashboard navigation for cloud cockpits.

Builds a Kibana **markdown** panel with curated deep-links into the EPR /
integration dashboards that ship with each cloud package, plus primary
Security / ML / CSPM jumps.

Note: ``custom_content`` strips ``<a>`` tags and sandboxes navigation, so
OOTB nav must be markdown for links to work.
"""

from __future__ import annotations

from typing import Any

# Stable panel indexes so re-imports stay idempotent across applies.
PANEL_IDS = {
    "gcp": "c0ffee01-6ee2-4c91-94f8-f034e8d34501",
    "aws": "c0ffee02-26e4-49d8-a2b4-548306880901",
    "azure": "c0ffee03-9a7d-4e3b-8c5a-1d6f0e9b2a01",
}

# Primary product deep-links shared by every cockpit.
PRIMARY_LINKS = [
    {"label": "Security alerts", "href": "/app/security/alerts", "tone": "alert"},
    {"label": "ML anomaly explorer", "href": "/app/ml/explorer", "tone": "warn"},
    {
        "label": "CSPM findings",
        "href": "/app/security/cloud_security_posture/findings/misconfigurations",
        "tone": "info",
    },
]

# Curated OOTB dashboards per cloud. IDs are the stable saved-object ids from
# the Elastic Package Registry integration packages (and live Kibana installs).
OOTB: dict[str, list[dict[str, Any]]] = {
    "gcp": [
        {
            "title": "Security & logs",
            "links": [
                ("Audit", "gcp-48e12760-cbe4-11ec-b519-85ccf621cbbf"),
                ("Firewall", "gcp-8a1fb690-cbeb-11ec-b519-85ccf621cbbf"),
                ("VPC Flow", "gcp-9484a4cd-685f-450e-aeaa-728fbdbea20f"),
            ],
        },
        {
            "title": "Compute & GKE",
            "links": [
                ("Compute", "gcp-f40ee870-5e4a-11ea-a4f6-717338406083"),
                ("GKE", "gcp-1ae960c0-f9f8-11eb-bc38-79936db7c106"),
                ("Cloud SQL MySQL", "gcp-c355cbb0-3a18-11ee-8736-83dacf143f01"),
                ("Cloud SQL PostgreSQL", "gcp-ddc19780-3a0a-11ee-8736-83dacf143f01"),
            ],
        },
        {
            "title": "Storage & networking",
            "links": [
                ("Storage", "gcp-ca401040-8e52-11ea-9fa6-4d675d5290dc"),
                ("Pub/Sub", "gcp-2b0fd7b0-feac-11ea-b032-d59f894a5072"),
                ("Load Balancing HTTPS", "gcp-aa5b8bd0-9157-11ea-8180-7b0dacd9df87"),
                ("Billing", "gcp-76c9e920-e890-11ea-bf8c-d13ebf358a78"),
            ],
        },
    ],
    "aws": [
        {
            "title": "Security & logs",
            "links": [
                ("CloudTrail", "aws-9c09cd20-7399-11ea-a345-f985c61fe654"),
                ("GuardDuty", "aws-9d21f520-6a36-11ed-b880-2f1b70138655"),
                ("Security Hub", "aws-c9f103d0-5f63-11ed-bd69-473ce047ef30"),
                ("VPC Flow", "aws-15503340-4488-11ea-ad63-791a5dc86f10"),
                ("WAF", "aws-3dc1a3a8-ae96-43aa-9065-074bda487262"),
                ("Config", "aws-5bbce111-827a-423f-b7b0-64ef13c28396"),
            ],
        },
        {
            "title": "Compute & data",
            "links": [
                ("Overview", "aws-fac28650-7349-11e9-816b-07687310a99a"),
                ("EC2", "aws-c5846400-f7fb-11e8-af03-c999c9dea608"),
                ("Lambda", "aws-7ac8e1d0-28d2-11ea-ba6c-49a884eb104f"),
                ("RDS", "aws-3367c170-921f-11e9-aa19-159bf182e06f"),
                ("DynamoDB", "aws-68ba7bd0-20b6-11ea-8f72-2f8d21e50b0c"),
            ],
        },
        {
            "title": "Storage & edge",
            "links": [
                ("S3", "aws-a096b830-4762-11e9-8062-c98a86cb6f94"),
                ("ALB", "aws-24f3e07a-b5f5-470c-8305-47c9626db37b"),
                ("Billing", "aws-e6776b10-1534-11ea-841c-01bf20a6c8ba"),
                ("Health", "aws-9574244b-b538-4cc1-9666-8aac4ecf433e"),
            ],
        },
    ],
    "azure": [
        {
            "title": "Security & identity",
            "links": [
                ("Cloud overview", "azure-41e84340-ec20-11e9-90ec-112a988266d5"),
                ("Alerts", "azure-0f559cc0-f0d5-11e9-90ec-112a988266d5"),
                ("User activity", "azure-87095750-f05a-11e9-90ec-112a988266d5"),
                ("Entra ID protection", "azure-5ee36c30-32dc-11ed-a2e6-916b60bbea71"),
                ("Microsoft Graph", "azure-2b2e94c8-aff5-401d-b9a5-aae2d051a92c"),
                ("Firewall overview", "azure-280493a0-f1a1-11ec-a5a8-bf965bcd5646"),
            ],
        },
        {
            "title": "Compute & containers",
            "links": [
                ("Compute VMs", "azure_metrics-eb3f05f0-ea9a-11e9-90ec-112a988266d5"),
                ("VM scale sets", "azure_metrics-91afcc50-eaad-11e9-90ec-112a988266d5"),
                ("Container service", "azure_metrics-dae20ed0-6d0a-11ea-8fe8-71add5fd7c38"),
                ("Container instances", "azure_metrics-9c11ac60-6cf6-11ea-8fe8-71add5fd7c38"),
            ],
        },
        {
            "title": "Storage & cost",
            "links": [
                ("Storage", "azure_metrics-1a151f80-32db-11ea-a83e-25b8612d00cc"),
                ("Blob storage", "azure_metrics-b165ef60-32f7-11ea-a83e-25b8612d00cc"),
                ("Database account", "azure_metrics-b232c220-8481-11ea-b181-4b1a9e0110f9"),
                ("Billing", "azure_billing-d3efeb30-c1c7-11ea-b7e7-0f48178cdb3c"),
            ],
        },
    ],
}

# Accent gradients aligned with each cockpit header banner.
THEMES = {
    "gcp": {
        "label": "Google Cloud",
        "kicker": "Integration dashboards",
        "gradient": "linear-gradient(120deg, #07141f 0%, #0b3d42 40%, #0b5e6b 70%, #1a73e8 100%)",
        "accent": "#48EFCF",
        "extra_primary": [],
    },
    "aws": {
        "label": "Amazon Web Services",
        "kicker": "Integration dashboards",
        "gradient": "linear-gradient(135deg, #0b1f3a 0%, #16324f 55%, #1e3a5f 100%)",
        "accent": "#48EFCF",
        "extra_primary": [
            {
                "label": "Recommendations",
                "href": "#aws-recommendations",
                "tone": "ok",
            }
        ],
    },
    "azure": {
        "label": "Microsoft Azure",
        "kicker": "Integration dashboards",
        "gradient": "linear-gradient(120deg, #07141f 0%, #0a2a4a 40%, #0078D4 100%)",
        "accent": "#48EFCF",
        "extra_primary": [
            {
                "label": "Recommendations",
                "href": "#azure-recommendations",
                "tone": "ok",
            }
        ],
    },
}

NAV_HEIGHT = 8  # markdown deep-link block (clickable; custom_content cannot host links)


def _dash_href(dashboard_id: str) -> str:
    return f"/app/dashboards#/view/{dashboard_id}"


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_template(cloud: str) -> str:
    cloud = cloud.lower()
    if cloud not in OOTB:
        raise ValueError(f"unsupported cloud: {cloud}")
    theme = THEMES[cloud]
    groups = OOTB[cloud]
    primary = list(PRIMARY_LINKS) + list(theme.get("extra_primary") or [])

    primary_md = " · ".join(
        f'[{link["label"]} →]({link["href"]})' for link in primary
    )
    group_blocks = []
    for group in groups:
        links = " · ".join(
            f"[{label}]({_dash_href(dash_id)})" for label, dash_id in group["links"]
        )
        group_blocks.append(f"**{group['title']}** · {links}")

    # Markdown (not custom_content) so links are clickable.
    return (
        f"### {theme['label']} OOTB dashboards\n"
        f"{theme.get('kicker', 'Integration dashboards')} — jump into package dashboards "
        f"and Security / ML / CSPM views.\n\n"
        f"**Primary** · {primary_md}\n\n"
        + "\n\n".join(group_blocks)
        + "\n"
    )


def build_panel(cloud: str, *, y: int = 8, x: int = 0, w: int = 48, h: int = NAV_HEIGHT) -> dict:
    """Return a markdown panel with clickable OOTB / Security deep-links."""
    cloud = cloud.lower()
    pid = PANEL_IDS[cloud]
    return {
        "type": "markdown",
        "panelIndex": pid,
        "gridData": {"y": y, "x": x, "w": w, "h": h, "i": pid},
        "embeddableConfig": {
            "title": "",
            "hidePanelTitles": True,
            "content": render_template(cloud),
            "settings": {"open_links_in_new_tab": False},
            "enhancements": {},
        },
    }


def is_quick_links_markdown(panel: dict) -> bool:
    """Detect the legacy emoji pipe-link markdown row we replace."""
    if panel.get("type") != "markdown":
        return False
    content = (panel.get("embeddableConfig") or {}).get("content") or ""
    return "Security Alerts" in content and "/app/security/alerts" in content


def inject_ootb_nav(panels: list[dict], cloud: str, *, y: int = 8) -> list[dict]:
    """Insert or replace the OOTB nav panel and shift panels below as needed.

    - Removes any prior OOTB nav panel (by stable id) and the legacy quick-links
      markdown row.
    - Inserts the new markdown nav panel at ``y``.
    - Shifts every other panel with ``gridData.y >= y`` down by ``NAV_HEIGHT``
      minus the height of removed panels that occupied that band (best-effort).
    """
    cloud = cloud.lower()
    nav_id = PANEL_IDS[cloud]
    removed_height = 0
    kept: list[dict] = []
    for p in panels:
        pid = p.get("panelIndex")
        gd = p.get("gridData") or {}
        if pid == nav_id:
            removed_height += int(gd.get("h") or 0)
            continue
        if is_quick_links_markdown(p) and int(gd.get("y") or 0) <= y + 2:
            removed_height += int(gd.get("h") or 0)
            continue
        kept.append(p)

    # Shift panels that sit at/after the insertion band.
    delta = NAV_HEIGHT - removed_height
    if delta != 0:
        for p in kept:
            gd = p.get("gridData") or {}
            if "sectionId" in gd:
                # Section-relative panels keep their local y; only absolute-y
                # panels on the main canvas need shifting.
                continue
            if int(gd.get("y") or 0) >= y:
                gd["y"] = int(gd["y"]) + delta

    kept.append(build_panel(cloud, y=y, h=NAV_HEIGHT))
    # Stable ordering: by y then x then panelIndex
    kept.sort(
        key=lambda p: (
            int((p.get("gridData") or {}).get("y") or 0),
            int((p.get("gridData") or {}).get("x") or 0),
            str(p.get("panelIndex") or ""),
        )
    )
    return kept
