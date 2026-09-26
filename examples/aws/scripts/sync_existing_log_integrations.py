#!/usr/bin/env python3
"""Reconcile Elastic policies for AWS logging sources already enabled by users."""

import base64
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request


KIBANA_URL = os.environ["KIBANA_URL"].rstrip("/")
AUTH = base64.b64encode(
    f"{os.environ['KIBANA_USERNAME']}:{os.environ['KIBANA_PASSWORD']}".encode()
).decode()
POLICY_PREFIX = "aws-existing-log-"


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


def package_policies() -> list[dict]:
    return request("GET", "/api/fleet/package_policies?perPage=10000").get(
        "items", []
    )


def cleanup() -> None:
    for item in package_policies():
        if item.get("name", "").startswith(POLICY_PREFIX):
            request(
                "DELETE",
                f"/api/fleet/package_policies/{item['id']}?force=true",
            )


def set_value(variables: dict, name: str, value) -> None:
    if name in variables:
        variables[name]["value"] = value


def policy_name(source: dict) -> str:
    digest = hashlib.sha256(
        json.dumps(source, sort_keys=True).encode()
    ).hexdigest()[:16]
    return f"{POLICY_PREFIX}{source['dataset'].removeprefix('aws.')}-{digest}"


def configure_stream(stream: dict, source: dict) -> None:
    variables = stream.get("vars", {})
    if source["kind"] == "cloudwatch":
        if "log_group_name_prefix" in source:
            set_value(
                variables,
                "log_group_name_prefix",
                source["log_group_name_prefix"],
            )
        else:
            set_value(variables, "log_group_name", source["log_group_name"])
        set_value(variables, "region_name", source["region"])
        set_value(variables, "preserve_original_event", False)
    else:
        set_value(variables, "collect_s3_logs", True)
        set_value(variables, "bucket_arn", f"arn:aws:s3:::{source['bucket']}")
        set_value(variables, "bucket_list_prefix", source.get("prefix", ""))
        set_value(variables, "interval", "1m")
        set_value(variables, "preserve_original_event", False)


def sync() -> None:
    sources: list[dict] = json.loads(os.environ["SOURCES_JSON"])
    policies = package_policies()
    existing = {item["name"]: item for item in policies}
    template = next(
        item for item in policies if item.get("name") == "aws-agent-only-integrations"
    )
    agent_policy_id = os.environ["AGENT_POLICY_ID"]
    desired_names = {policy_name(source) for source in sources}

    # Remove policies for sources where customer-side logging was disabled.
    for name, item in existing.items():
        if name.startswith(POLICY_PREFIX) and name not in desired_names:
            request(
                "DELETE",
                f"/api/fleet/package_policies/{item['id']}?force=true",
            )

    def reconcile(source: dict) -> None:
        name = policy_name(source)
        body = {
            "name": name,
            "namespace": "default",
            "description": (
                f"Existing {source['dataset']} source in {source['region']}"
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
        body["vars"]["default_region"]["value"] = source["region"]
        policy_token = hashlib.sha256(name.encode()).hexdigest()[:12]

        for input_index, input_config in enumerate(body["inputs"]):
            input_config["id"] = (
                f"{input_config['type']}-{policy_token}-{input_index}"
            )
            enabled_input = (
                input_config.get("policy_template") == source["policy_template"]
                and input_config.get("type") == source["input_type"]
            )
            input_config["enabled"] = enabled_input
            for stream_index, stream in enumerate(input_config.get("streams", [])):
                stream["id"] = (
                    f"{input_config['type']}-{policy_token}"
                    f"-{input_index}-{stream_index}"
                )
                enabled_stream = (
                    enabled_input
                    and stream["data_stream"]["dataset"] == source["dataset"]
                )
                stream["enabled"] = enabled_stream
                if enabled_stream:
                    configure_stream(stream, source)

        if name in existing:
            request(
                "PUT",
                f"/api/fleet/package_policies/{existing[name]['id']}",
                body,
            )
        else:
            request("POST", "/api/fleet/package_policies", body)

    # Fleet handles a small amount of package-policy concurrency reliably and
    # this keeps accounts with many existing log groups practical.
    with ThreadPoolExecutor(max_workers=5) as executor:
        list(executor.map(reconcile, sources))


if len(sys.argv) != 2 or sys.argv[1] not in {"sync", "cleanup"}:
    raise SystemExit("usage: sync_existing_log_integrations.py sync|cleanup")

sync() if sys.argv[1] == "sync" else cleanup()
