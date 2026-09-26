#!/usr/bin/env python3
"""Return active GuardDuty detector IDs keyed by AWS region for Terraform."""

from concurrent.futures import ThreadPoolExecutor, as_completed
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
        timeout=20,
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

def detector_for_region(region: dict[str, str]) -> tuple[str, str] | None:
    if region.get("OptInStatus") == "not-opted-in":
        return None

    region_name = region["RegionName"]
    try:
        ids = aws(
            "guardduty",
            "list-detectors",
            "--region",
            region_name,
        )["DetectorIds"]
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        # GuardDuty is not available in every AWS region.
        return None

    if ids:
        return region_name, ids[0]
    return None


detectors: dict[str, str] = {}
with ThreadPoolExecutor(max_workers=10) as executor:
    futures = [executor.submit(detector_for_region, region) for region in regions]
    for future in as_completed(futures):
        result = future.result()
        if result:
            detectors[result[0]] = result[1]

json.dump(detectors, sys.stdout, sort_keys=True)
