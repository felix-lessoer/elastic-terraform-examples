#!/usr/bin/env python3
"""Enable Security Hub and reconcile one managed integration per AWS region."""

import base64
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
        timeout=120,
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


def cleanup() -> None:
    for item in managed_integrations():
        if item.get("name", "").startswith(f"{NAME_PREFIX}-securityhub-"):
            request(
                "DELETE",
                f"/api/fleet/managed_integrations/{item['id']}?force=true",
            )


def ensure_security_hub(region: str) -> bool:
    try:
        aws("securityhub", "describe-hub", "--region", region)
        return True
    except subprocess.CalledProcessError:
        try:
            aws("securityhub", "enable-security-hub", "--region", region)
            return True
        except subprocess.CalledProcessError:
            # Security Hub is not offered in every enabled AWS region.
            return False


def sync() -> None:
    regions: list[str] = json.loads(os.environ["REGIONS_JSON"])
    existing = {item["name"]: item for item in managed_integrations()}
    connectors = {
        item["name"]: item
        for item in request(
            "GET", "/api/fleet/cloud_connectors?perPage=10000"
        ).get("items", [])
    }
    package_version = request("GET", "/api/fleet/epm/packages/aws")["item"][
        "version"
    ]
    role_arn = os.environ["AWS_ROLE_ARN"]

    for region in sorted(regions):
        if not ensure_security_hub(region):
            continue

        name = f"{NAME_PREFIX}-securityhub-{region}"
        if name in existing:
            continue

        connector = connectors.get(name)
        cloud_connector = {"enabled": True, "target_csp": "aws"}
        if connector:
            cloud_connector["cloud_connector_id"] = connector["id"]
        else:
            cloud_connector["name"] = name

        common_vars = {
            "aws_region": region,
            "tld": "amazonaws.com",
            "preserve_original_event": False,
            "preserve_duplicate_custom_fields": False,
        }
        request(
            "POST",
            "/api/fleet/managed_integrations",
            {
                "name": name,
                "namespace": "default",
                "description": (
                    f"Elastic-managed Security Hub CSPM collection in {region}"
                ),
                "policy_template": "securityhub",
                "package": {"name": "aws", "version": package_version},
                "vars": {
                    "default_region": region,
                    "role_arn": role_arn,
                    "supports_identity_federation": True,
                },
                "var_group_selections": {
                    "credential_type": "identity_federation"
                },
                "cloud_connector": cloud_connector,
                "inputs": {
                    "securityhub-httpjson": {
                        "enabled": True,
                        "streams": {
                            "aws.securityhub_findings": {
                                "enabled": True,
                                "vars": {
                                    **common_vars,
                                    "interval": "1h",
                                    "initial_interval": "24h",
                                    "tags": [
                                        "forwarded",
                                        "aws_securityhub_findings",
                                    ],
                                },
                            },
                            "aws.securityhub_findings_full_posture": {
                                "enabled": True,
                                "vars": {
                                    **common_vars,
                                    "tags": [
                                        "forwarded",
                                        "aws_securityhub_findings_full_posture",
                                    ],
                                },
                            },
                            "aws.securityhub_insights": {
                                "enabled": True,
                                "vars": {
                                    **common_vars,
                                    "interval": "1m",
                                    "tags": [
                                        "forwarded",
                                        "aws_securityhub_insights",
                                    ],
                                },
                            },
                        },
                    }
                },
            },
        )


if len(sys.argv) != 2 or sys.argv[1] not in {"sync", "cleanup"}:
    raise SystemExit("usage: sync_securityhub_integrations.py sync|cleanup")

sync() if sys.argv[1] == "sync" else cleanup()
