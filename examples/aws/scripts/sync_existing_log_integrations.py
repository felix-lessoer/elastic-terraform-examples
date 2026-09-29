#!/usr/bin/env python3
"""Reconcile Elastic policies for AWS logging sources already enabled by users."""

import base64
from concurrent.futures import ThreadPoolExecutor
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


KIBANA_URL = os.environ.get("KIBANA_URL", "").rstrip("/")
AUTH = base64.b64encode(
    (
        f"{os.environ.get('KIBANA_USERNAME', '')}:"
        f"{os.environ.get('KIBANA_PASSWORD', '')}"
    ).encode()
).decode()
POLICY_PREFIX = os.environ.get("POLICY_PREFIX", "aws-existing-log-")
MAX_STREAMS_PER_POLICY = int(os.environ.get("MAX_STREAMS_PER_POLICY", "50"))


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
    for attempt in range(1, 8):
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                payload = response.read()
                return json.loads(payload) if payload else {}
        except urllib.error.HTTPError as error:
            detail = error.read().decode()
            if error.code == 409 and attempt < 7:
                time.sleep(attempt * 2)
                continue
            raise RuntimeError(
                f"{method} {path} failed ({error.code}): {detail}"
            ) from error
    raise RuntimeError(f"{method} {path} exhausted conflict retries")


def package_policies() -> list[dict]:
    items: list[dict] = []
    page = 1
    page_size = 100
    while True:
        response = request(
            "GET",
            "/api/fleet/package_policies?"
            + urllib.parse.urlencode({"page": page, "perPage": page_size}),
        )
        batch = response.get("items", [])
        items.extend(batch)
        total = response.get("total")
        if not batch or (isinstance(total, int) and len(items) >= total):
            return items
        if len(batch) < page_size:
            return items
        page += 1


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


def source_group_key(source: dict) -> tuple[str, ...]:
    return (
        source["kind"],
        source["region"],
        source["policy_template"],
        source["input_type"],
        source["dataset"],
    )


def policy_name(group_key: tuple[str, ...], chunk: int) -> str:
    digest = hashlib.sha256(
        json.dumps(group_key, sort_keys=True).encode()
    ).hexdigest()[:16]
    dataset = group_key[-1].removeprefix("aws.")
    region = group_key[1]
    return f"{POLICY_PREFIX}{dataset}-{region}-{digest}-{chunk + 1}"


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
        set_value(
            variables,
            "start_timestamp",
            (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(),
        )
        set_value(variables, "ignore_older", "24h")
        set_value(variables, "preserve_original_event", False)


def desired_policy_groups(
    sources: list[dict],
) -> list[tuple[str, list[dict]]]:
    grouped: dict[tuple[str, ...], list[dict]] = {}
    for source in sources:
        grouped.setdefault(source_group_key(source), []).append(source)
    desired: list[tuple[str, list[dict]]] = []
    for group_key, group_sources in sorted(grouped.items()):
        ordered = sorted(
            group_sources,
            key=lambda source: json.dumps(source, sort_keys=True),
        )
        for offset in range(0, len(ordered), MAX_STREAMS_PER_POLICY):
            chunk = offset // MAX_STREAMS_PER_POLICY
            desired.append(
                (
                    policy_name(group_key, chunk),
                    ordered[offset : offset + MAX_STREAMS_PER_POLICY],
                )
            )
    return desired


def sync(*, preserve_unselected: bool = False) -> None:
    sources: list[dict] = json.loads(os.environ["SOURCES_JSON"])
    policies = package_policies()
    existing = {item["name"]: item for item in policies}
    template = next(
        item for item in policies if item.get("name") == "aws-agent-only-integrations"
    )
    agent_policy_id = os.environ["AGENT_POLICY_ID"]
    desired = desired_policy_groups(sources)
    desired_names = {name for name, _ in desired}

    def reconcile(item: tuple[str, list[dict]]) -> None:
        name, policy_sources = item
        exemplar = policy_sources[0]
        body = {
            "name": name,
            "namespace": "default",
            "description": (
                f"{len(policy_sources)} existing {exemplar['dataset']} "
                f"sources in {exemplar['region']}"
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
        body["vars"]["default_region"]["value"] = exemplar["region"]
        policy_token = hashlib.sha256(name.encode()).hexdigest()[:12]

        for input_index, input_config in enumerate(body["inputs"]):
            input_config["id"] = (
                f"{input_config['type']}-{policy_token}-{input_index}"
            )
            enabled_input = (
                input_config.get("policy_template")
                == exemplar["policy_template"]
                and input_config.get("type") == exemplar["input_type"]
            )
            input_config["enabled"] = enabled_input
            if enabled_input:
                stream_template = next(
                    stream
                    for stream in input_config.get("streams", [])
                    if stream["data_stream"]["dataset"] == exemplar["dataset"]
                )
                input_config["streams"] = []
                for stream_index, source in enumerate(policy_sources):
                    stream = copy.deepcopy(stream_template)
                    stream["id"] = (
                        f"{input_config['type']}-{policy_token}"
                        f"-{input_index}-{stream_index}"
                    )
                    stream["enabled"] = True
                    configure_stream(stream, source)
                    input_config["streams"].append(stream)
            else:
                for stream_index, stream in enumerate(
                    input_config.get("streams", [])
                ):
                    stream["id"] = (
                        f"{input_config['type']}-{policy_token}"
                        f"-{input_index}-{stream_index}"
                    )
                    stream["enabled"] = False

        if name in existing:
            request(
                "PUT",
                f"/api/fleet/package_policies/{existing[name]['id']}",
                body,
            )
        else:
            request("POST", "/api/fleet/package_policies", body)

    # Reconcile grouped policies first so collection remains present while old
    # per-source policies are removed.
    with ThreadPoolExecutor(max_workers=5) as executor:
        list(executor.map(reconcile, desired))

    if not preserve_unselected:
        for name, item in existing.items():
            if name.startswith(POLICY_PREFIX) and name not in desired_names:
                request(
                    "DELETE",
                    f"/api/fleet/package_policies/{item['id']}?force=true",
                )

def cleanup_selected() -> None:
    sources: list[dict] = json.loads(os.environ["SOURCES_JSON"])
    selected_groups = {source_group_key(source) for source in sources}
    for item in package_policies():
        name = item.get("name", "")
        if any(
            name.startswith(
                f"{POLICY_PREFIX}{group[-1].removeprefix('aws.')}-{group[1]}-"
            )
            for group in selected_groups
        ):
            request(
                "DELETE",
                f"/api/fleet/package_policies/{item['id']}?force=true",
            )


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {
        "sync",
        "sync-selected",
        "cleanup",
        "cleanup-selected",
    }:
        raise SystemExit(
            "usage: sync_existing_log_integrations.py "
            "sync|sync-selected|cleanup|cleanup-selected"
        )

    if sys.argv[1] == "sync":
        sync()
    elif sys.argv[1] == "sync-selected":
        sync(preserve_unselected=True)
    elif sys.argv[1] == "cleanup-selected":
        cleanup_selected()
    else:
        cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
