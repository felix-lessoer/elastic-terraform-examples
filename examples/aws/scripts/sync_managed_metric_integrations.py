#!/usr/bin/env python3
"""Serially reconcile Elastic-managed AWS metric integrations."""

import base64
import json
import os
import sys
import urllib.error
import urllib.request


KIBANA_URL = os.environ["KIBANA_URL"].rstrip("/")
AUTH = base64.b64encode(
    f"{os.environ['KIBANA_USERNAME']}:{os.environ['KIBANA_PASSWORD']}".encode()
).decode()
POLICY_SUFFIX = "-all-regions"


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


def integrations() -> list[dict]:
    return request(
        "GET", "/api/fleet/managed_integrations?perPage=10000"
    ).get("items", [])


def cleanup() -> None:
    for item in integrations():
        name = item.get("name", "")
        if name.startswith("aws-managed-") and name.endswith(POLICY_SUFFIX):
            request(
                "DELETE",
                f"/api/fleet/managed_integrations/{item['id']}?force=true",
            )


def decode_vars(inputs: dict) -> dict:
    for input_config in inputs.values():
        for stream in input_config.get("streams", {}).values():
            if isinstance(stream.get("vars"), str):
                stream["vars"] = json.loads(stream["vars"])
    return inputs


def sync() -> None:
    specs: list[dict] = json.loads(os.environ["SPECS_JSON"])
    existing = {item["name"]: item for item in integrations()}
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

    for spec in sorted(specs, key=lambda item: item["name"]):
        name = spec["name"]
        if name in existing:
            continue

        connector_name = spec["connector_name"]
        connector = connectors.get(connector_name)
        cloud_connector = {"enabled": True, "target_csp": "aws"}
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
                "description": spec["description"],
                "policy_template": spec["policy_template"],
                "package": {"name": "aws", "version": package_version},
                "vars": {
                    "default_region": spec["default_region"],
                    "role_arn": role_arn,
                    "supports_identity_federation": True,
                },
                "var_group_selections": {
                    "credential_type": "identity_federation"
                },
                "cloud_connector": cloud_connector,
                "inputs": decode_vars(spec["inputs"]),
            },
        )


if len(sys.argv) != 2 or sys.argv[1] not in {"sync", "cleanup"}:
    raise SystemExit("usage: sync_managed_metric_integrations.py sync|cleanup")

sync() if sys.argv[1] == "sync" else cleanup()
