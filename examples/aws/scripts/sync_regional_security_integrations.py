#!/usr/bin/env python3
"""Reconcile regional AWS security API integrations on one Elastic Agent."""

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
AWS_CLI = shutil.which("aws") or str(Path.home() / ".local" / "bin" / "aws")
POLICY_PREFIX = "aws-regional-security-"


def aws(*args: str, timeout: int = 30) -> dict:
    result = subprocess.run(
        [AWS_CLI, *args, "--output", "json"],
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
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


def remove_legacy_policies() -> None:
    for item in managed_integrations():
        name = item.get("name", "")
        if name.startswith("aws-managed-guardduty-") or name.startswith(
            "aws-managed-securityhub-"
        ):
            request(
                "DELETE",
                f"/api/fleet/managed_integrations/{item['id']}?force=true",
            )

    for item in package_policies():
        name = item.get("name", "")
        if name.startswith("aws-securityhub-"):
            request(
                "DELETE",
                f"/api/fleet/package_policies/{item['id']}?force=true",
            )


def cleanup() -> None:
    remove_legacy_policies()
    for item in package_policies():
        if item.get("name", "").startswith(POLICY_PREFIX):
            request(
                "DELETE",
                f"/api/fleet/package_policies/{item['id']}?force=true",
            )


def ensure_guardduty(region: str, detector_id: str) -> str:
    if detector_id:
        return detector_id
    return aws(
        "guardduty",
        "create-detector",
        "--region",
        region,
        "--enable",
        "--finding-publishing-frequency",
        "FIFTEEN_MINUTES",
        "--tags",
        "ManagedBy=terraform,ElasticProject=elastic-observability",
    )["DetectorId"]


def ensure_security_hub(region: str) -> bool:
    try:
        aws("securityhub", "describe-hub", "--region", region)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        try:
            aws("securityhub", "enable-security-hub", "--region", region)
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False


def enable_inspector(region: str, account_id: str) -> None:
    # Inspector is not offered in every region/resource-type combination.
    # Collection remains enabled even when service activation is unsupported.
    try:
        aws(
            "inspector2",
            "batch-enable",
            "--region",
            region,
            "--account-ids",
            account_id,
            "--resource-types",
            "EC2",
            "ECR",
            "LAMBDA",
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass


def bootstrap_region(
    region: str, detector_id: str, account_id: str
) -> tuple[str, str] | None:
    try:
        detector_id = ensure_guardduty(region, detector_id)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    ensure_security_hub(region)
    enable_inspector(region, account_id)
    return region, detector_id


def set_value(variables: dict, name: str, value) -> None:
    if name in variables:
        variables[name]["value"] = value


def configure_stream(stream: dict, region: str, detector_id: str) -> None:
    dataset = stream["data_stream"]["dataset"]
    variables = stream.get("vars", {})
    set_value(variables, "aws_region", region)

    if dataset == "aws.guardduty":
        set_value(variables, "detector_id", detector_id)
        set_value(variables, "interval", "1m")
        set_value(variables, "initial_interval", "24h")
    elif dataset == "aws.inspector":
        set_value(variables, "interval", "24h")
        set_value(variables, "initial_interval", "2160h")
    elif dataset == "aws.securityhub_findings":
        set_value(variables, "interval", "1h")
        set_value(variables, "initial_interval", "24h")
    elif dataset == "aws.securityhub_insights":
        set_value(variables, "interval", "1m")
    elif dataset == "aws.config":
        set_value(variables, "interval", "24h")


def sync() -> None:
    regions: list[str] = json.loads(os.environ["REGIONS_JSON"])
    detectors: dict[str, str] = json.loads(os.environ["DETECTORS_JSON"])
    account_id = os.environ["AWS_ACCOUNT_ID"]

    regional_detectors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(
                bootstrap_region,
                region,
                detectors.get(region, ""),
                account_id,
            ): region
            for region in regions
        }
        for future in as_completed(futures):
            result = future.result()
            if result:
                regional_detectors[result[0]] = result[1]

    remove_legacy_policies()
    policies = package_policies()
    existing = {item["name"]: item for item in policies}
    template = next(
        item for item in policies if item.get("name") == "aws-agent-only-integrations"
    )
    agent_policy_id = os.environ["AGENT_POLICY_ID"]
    security_templates = {"config", "guardduty", "inspector", "securityhub"}

    for region, detector_id in sorted(regional_detectors.items()):
        name = f"{POLICY_PREFIX}{region}"
        if name in existing:
            continue

        body = {
            "name": name,
            "namespace": "default",
            "description": (
                f"GuardDuty, Security Hub, Inspector, and Config in {region}"
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
            enabled = input_config.get("policy_template") in security_templates
            input_config["enabled"] = enabled
            for stream in input_config.get("streams", []):
                stream["enabled"] = enabled
                if enabled:
                    configure_stream(stream, region, detector_id)

        request("POST", "/api/fleet/package_policies", body)


if len(sys.argv) != 2 or sys.argv[1] not in {"sync", "cleanup"}:
    raise SystemExit("usage: sync_regional_security_integrations.py sync|cleanup")

sync() if sys.argv[1] == "sync" else cleanup()
