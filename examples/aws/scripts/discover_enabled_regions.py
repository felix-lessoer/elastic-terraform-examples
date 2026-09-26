#!/usr/bin/env python3
"""Return customer-enabled AWS regions keyed by region name for Terraform."""

import json
from pathlib import Path
import shutil
import subprocess
import sys


query = json.load(sys.stdin)
aws_cli = shutil.which("aws") or str(Path.home() / ".local" / "bin" / "aws")
result = subprocess.run(
    [
        aws_cli,
        "ec2",
        "describe-regions",
        "--region",
        query["bootstrap_region"],
        "--all-regions",
        "--output",
        "json",
    ],
    check=True,
    capture_output=True,
    text=True,
    timeout=120,
)

regions = {
    item["RegionName"]: item["RegionName"]
    for item in json.loads(result.stdout)["Regions"]
    if item.get("OptInStatus") != "not-opted-in"
}
json.dump(regions, sys.stdout, sort_keys=True)
