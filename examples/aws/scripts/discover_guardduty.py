#!/usr/bin/env python3
"""Return active GuardDuty detector IDs keyed by AWS region for Terraform."""

import json
from pathlib import Path
import shutil
import subprocess
import sys

AWS_CLI = shutil.which("aws") or str(Path.home() / ".local" / "bin" / "aws")


def aws(*args: str) -> dict:
    result = subprocess.run(
        [AWS_CLI, *args, "--output", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


query = json.load(sys.stdin)
bootstrap_region = query["bootstrap_region"]

regions = aws(
    "ec2",
    "describe-regions",
    "--region",
    bootstrap_region,
    "--all-regions",
)["Regions"]

detectors: dict[str, str] = {}
for region in regions:
    if region.get("OptInStatus") == "not-opted-in":
        continue

    region_name = region["RegionName"]
    try:
        ids = aws(
            "guardduty",
            "list-detectors",
            "--region",
            region_name,
        )["DetectorIds"]
    except subprocess.CalledProcessError:
        # GuardDuty is not available in every AWS region.
        continue

    if ids:
        detectors[region_name] = ids[0]

json.dump(detectors, sys.stdout, sort_keys=True)
