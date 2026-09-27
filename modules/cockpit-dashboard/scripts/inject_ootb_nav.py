#!/usr/bin/env python3
"""Inject OOTB custom_content navigation into cockpit NDJSON exports."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ootb_nav import PANEL_IDS, inject_ootb_nav

ROOT = Path(__file__).resolve().parents[1]

TARGETS = {
    "gcp": ROOT / "cockpit.ndjson",
    "aws": ROOT / "cockpit-aws.ndjson",
    "azure": ROOT / "cockpit-azure.ndjson",
}


def patch_file(path: Path, cloud: str) -> None:
    lines = path.read_text().splitlines(keepends=True)
    out_lines: list[str] = []
    patched = False
    for line in lines:
        raw = line.strip()
        if not raw:
            out_lines.append(line)
            continue
        obj = json.loads(raw)
        attrs = obj.get("attributes") or {}
        if "panelsJSON" not in attrs:
            out_lines.append(line if line.endswith("\n") else line + "\n")
            continue
        panels = json.loads(attrs["panelsJSON"])
        panels = inject_ootb_nav(panels, cloud)
        attrs["panelsJSON"] = json.dumps(panels, separators=(",", ":"))
        obj["attributes"] = attrs
        # Preserve single-line NDJSON style used by Kibana export.
        out_lines.append(json.dumps(obj, separators=(",", ":")) + "\n")
        patched = True
    if not patched:
        raise SystemExit(f"no dashboard panelsJSON found in {path}")
    path.write_text("".join(out_lines))
    print(f"patched {path.name}: OOTB nav panel {PANEL_IDS[cloud]}")


def main(argv: list[str]) -> int:
    clouds = argv[1:] or list(TARGETS)
    for cloud in clouds:
        cloud = cloud.lower()
        if cloud not in TARGETS:
            raise SystemExit(f"unknown cloud {cloud}; choose from {list(TARGETS)}")
        patch_file(TARGETS[cloud], cloud)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
