#!/usr/bin/env python3
"""Enable Security Hub and reconcile one managed integration per AWS region."""

import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.error
import urllib.request


KIBANA_URL = os.environ["KIBANA_URL"].rstrip("/")
AUTH = base64.b64encode(
    f"{os.environ['KIBANA_USERNAME']}:{os.environ['KIBANA_PASSWORD']}".encode()
).decode()
NAME_PREFIX = os.environ["NAME_PREFIX"]
AWS_CLI = shutil.which("aws") or str(Path.home() / ".local" / "bin" / "aws")


def aws(*args: str) -> dict:
    result = subprocess.run(
        [AWS_CLI, *args, "--output", "json"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return json.loads(result.stdout)


def request(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{KIBANA_URL}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Basic {AUTH}",
            "Content-Type": "application/json",
            "kbn-xsrf": "true",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            payload = response.read()
            return json.loads(payload) if payload else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode()
        raise RuntimeError(f"{method} {path} failed ({error.code}): {detail}") from error


def managed_integrations() -> list[dict]:
    return request(
        "GET", "/api/fleet/managed_integrations?perPage=10000"
    ).get("items", [])


def package_policies() -> list[dict]:
    return request("GET", "/api/fleet/package_policies?perPage=10000").get(
        "items", []
    )


def cleanup_managed() -> None:
    for item in managed_integrations():
        if item.get("name", "").startswith("aws-managed-securityhub-"):
            request(
                "DELETE",
                f"/api/fleet/managed_integrations/{item['id']}?force=true",
            )


def cleanup() -> None:
    cleanup_managed()
    for item in package_policies():
        if item.get("name", "").startswith(f"{NAME_PREFIX}-securityhub-"):
            request(
                "DELETE",
                f"/api/fleet/package_policies/{item['id']}?force=true",
            )


def ensure_security_hub(region: str) -> bool:
    try:
        aws("securityhub", "describe-hub", "--region", region)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        try:
            aws("securityhub", "enable-security-hub", "--region", region)
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            # Security Hub is not offered in every enabled AWS region.
            return False


def sync() -> None:
    regions: list[str] = json.loads(os.environ["REGIONS_JSON"])

    supported_regions: list[str] = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(ensure_security_hub, region): region
            for region in regions
        }
        for future in as_completed(futures):
            if future.result():
                supported_regions.append(futures[future])

    # Security Hub runs on the shared EC2 Agent to avoid the Serverless
    # managed-runtime limit. Remove managed policies from older revisions.
    cleanup_managed()

    policies = package_policies()
    existing = {item["name"]: item for item in policies}
    template = next(
        item for item in policies if item.get("name") == "aws-agent-only-integrations"
    )
    agent_policy_id = os.environ["AGENT_POLICY_ID"]

    for region in sorted(supported_regions):
        name = f"{NAME_PREFIX}-securityhub-{region}"
        if name in existing:
            continue

        body = {
            "name": name,
            "namespace": "default",
            "description": (
                f"Security Hub CSPM collection in {region} on the shared EC2 Agent"
            ),
            "package": {
                "name": template["package"]["name"],
                "version": template["package"]["version"],
            },
            "enabled": True,
            "policy_id": agent_policy_id,
            "inputs": copy.deepcopy(template["inputs"]),
            "vars": copy.deepcopy(template["vars"]),
        }
        body["vars"]["default_region"]["value"] = region

        for input_config in body["inputs"]:
            input_config["enabled"] = False
            for stream in input_config.get("streams", []):
                stream["enabled"] = False

            if input_config.get("policy_template") != "securityhub":
                continue

            input_config["enabled"] = True
            for stream in input_config["streams"]:
                stream["enabled"] = True
                dataset = stream["data_stream"]["dataset"]
                variables = stream["vars"]
                variables["aws_region"]["value"] = region
                if dataset == "aws.securityhub_findings":
                    variables["interval"]["value"] = "1h"
                    variables["initial_interval"]["value"] = "24h"
                elif dataset == "aws.securityhub_insights":
                    variables["interval"]["value"] = "1m"

        request("POST", "/api/fleet/package_policies", body)


if len(sys.argv) != 2 or sys.argv[1] not in {"sync", "cleanup"}:
    raise SystemExit("usage: sync_securityhub_integrations.py sync|cleanup")

sync() if sys.argv[1] == "sync" else cleanup()
