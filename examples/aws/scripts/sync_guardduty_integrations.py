#!/usr/bin/env python3
"""Idempotently reconcile regional GuardDuty managed integrations in Kibana."""

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
    return request("GET", "/api/fleet/managed_integrations").get("items", [])


def cleanup() -> None:
    for item in managed_integrations():
        if item.get("name", "").startswith(f"{NAME_PREFIX}-guardduty-"):
            request(
                "DELETE",
                f"/api/fleet/managed_integrations/{item['id']}?force=true",
            )


def sync() -> None:
    detectors: dict[str, str] = json.loads(os.environ["DETECTORS_JSON"])
    existing = {item["name"]: item for item in managed_integrations()}
    connectors = {
        item["name"]: item
        for item in request(
            "GET", "/api/fleet/cloud_connectors?perPage=10000"
        ).get("items", [])
    }
    package = request("GET", "/api/fleet/epm/packages/aws")["item"]
    package_version = package["version"]
    role_arn = os.environ["AWS_ROLE_ARN"]

    for region, detector_id in sorted(detectors.items()):
        if not detector_id:
            detector_id = aws(
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

        name = f"{NAME_PREFIX}-guardduty-{region}"
        if name in existing:
            continue

        connector_name = f"{NAME_PREFIX}-guardduty-{region}"
        connector = connectors.get(connector_name)
        cloud_connector = {
            "enabled": True,
            "target_csp": "aws",
        }
        if connector:
            cloud_connector["cloud_connector_id"] = connector["id"]
        else:
            cloud_connector["name"] = connector_name

        request(
            "POST",
            "/api/fleet/managed_integrations",
            {
                "name": name,
                "namespace": "default",
                "description": (
                    f"Elastic-managed GuardDuty findings collection in {region}"
                ),
                "policy_template": "guardduty",
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
                    "guardduty-httpjson": {
                        "enabled": True,
                        "streams": {
                            "aws.guardduty": {
                                "enabled": True,
                                "vars": {
                                    "interval": "1m",
                                    "initial_interval": "24h",
                                    "detector_id": detector_id,
                                    "aws_region": region,
                                    "tld": "amazonaws.com",
                                    "http_client_timeout": "30s",
                                    "tags": ["forwarded", "aws-guardduty"],
                                    "preserve_original_event": False,
                                    "preserve_duplicate_custom_fields": False,
                                },
                            }
                        },
                    },
                    "guardduty-aws-s3": {
                        "enabled": False,
                        "streams": {"aws.guardduty": {"enabled": False}},
                    },
                },
            },
        )


if len(sys.argv) != 2 or sys.argv[1] not in {"sync", "cleanup"}:
    raise SystemExit("usage: sync_guardduty_integrations.py sync|cleanup")

sync() if sys.argv[1] == "sync" else cleanup()
