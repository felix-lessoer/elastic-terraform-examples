#!/usr/bin/env python3
"""Create or migrate AWS cockpit reference indices to lookup mode."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from base64 import b64encode
from copy import deepcopy


LOOKUP_INDICES = {
    "aws-cockpit-assets": {
        "resource": {
            "properties": {
                "key": {"type": "keyword"},
                "type": {"type": "keyword"},
                "name": {"type": "keyword"},
                "id": {"type": "keyword"},
            }
        }
    },
    "aws-cockpit-recommendations": {
        "category": {"type": "keyword"},
        "severity": {"type": "keyword"},
        "resource": {
            "properties": {
                "key": {"type": "keyword"},
                "type": {"type": "keyword"},
                "name": {"type": "keyword"},
                "id": {"type": "keyword"},
            }
        },
    },
    "aws-cockpit-coverage": {
        "service": {"type": "keyword"},
        "lookup": {"properties": {"key": {"type": "keyword"}}},
    },
    "aws-cockpit-dataset-coverage": {
        "service": {"type": "keyword"},
        "lookup": {"properties": {"key": {"type": "keyword"}}},
    },
    "aws-cockpit-insight-summary": {
        "level": {"type": "keyword"},
        "lookup": {"properties": {"key": {"type": "keyword"}}},
    },
}


class Elasticsearch:
    def __init__(self, endpoint: str, user: str, password: str):
        self.endpoint = endpoint.rstrip("/")
        self.authorization = "Basic " + b64encode(
            f"{user}:{password}".encode()
        ).decode()

    def request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        *,
        allow_not_found: bool = False,
    ) -> dict | None:
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(
            f"{self.endpoint}/{path.lstrip('/')}",
            data=data,
            headers={
                "Authorization": self.authorization,
                "Content-Type": "application/json",
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = response.read()
                return json.loads(payload) if payload else {}
        except urllib.error.HTTPError as error:
            detail = error.read().decode()
            if allow_not_found and error.code == 404:
                return None
            raise RuntimeError(
                f"{method} {path} failed ({error.code}): {detail[:500]}"
            ) from error


def merge_properties(current: dict, required: dict) -> dict:
    merged = deepcopy(current)
    for field, definition in required.items():
        if field not in merged:
            merged[field] = deepcopy(definition)
            continue
        if "properties" in definition:
            merged[field]["properties"] = merge_properties(
                merged[field].get("properties", {}),
                definition["properties"],
            )
    return merged


def create_lookup_index(
    client: Elasticsearch, index: str, mappings: dict
) -> None:
    client.request(
        "PUT",
        index,
        {
            "settings": {"index.mode": "lookup"},
            "mappings": mappings,
        },
    )


def count(client: Elasticsearch, index: str) -> int:
    result = client.request("GET", f"{index}/_count")
    return int((result or {}).get("count", 0))


def reindex(client: Elasticsearch, source: str, destination: str) -> None:
    client.request(
        "POST",
        "_reindex?wait_for_completion=true&refresh=true",
        {
            "conflicts": "proceed",
            "source": {"index": source},
            "dest": {"index": destination},
        },
    )


def migrate_index(
    client: Elasticsearch, index: str, required_properties: dict
) -> str:
    current = client.request("GET", index, allow_not_found=True)
    migration = f"{index}-lookup-migration"

    if current is None:
        staged = client.request("GET", migration, allow_not_found=True)
        mappings = {"properties": deepcopy(required_properties)}
        if staged is not None:
            staged_index = staged[migration]
            mappings = deepcopy(staged_index.get("mappings", mappings))
        create_lookup_index(client, index, mappings)
        if staged is not None:
            reindex(client, migration, index)
            if count(client, index) != count(client, migration):
                raise RuntimeError(f"{index}: recovery document count mismatch")
            client.request("DELETE", migration)
            return "recovered"
        return "created"

    metadata = current[index]
    mode = (
        metadata.get("settings", {})
        .get("index", {})
        .get("mode", "standard")
    )
    properties = merge_properties(
        metadata.get("mappings", {}).get("properties", {}),
        required_properties,
    )
    mappings = deepcopy(metadata.get("mappings", {}))
    mappings["properties"] = properties

    if mode == "lookup":
        client.request("PUT", f"{index}/_mapping", {"properties": properties})
        if client.request("GET", migration, allow_not_found=True) is not None:
            client.request("DELETE", migration)
        return "ready"

    if client.request("GET", migration, allow_not_found=True) is not None:
        client.request("DELETE", migration)
    create_lookup_index(client, migration, mappings)
    reindex(client, index, migration)
    source_count = count(client, index)
    if count(client, migration) != source_count:
        raise RuntimeError(f"{index}: staged document count mismatch")

    client.request("DELETE", index)
    create_lookup_index(client, index, mappings)
    reindex(client, migration, index)
    if count(client, index) != source_count:
        raise RuntimeError(f"{index}: migrated document count mismatch")
    client.request("DELETE", migration)
    return "migrated"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--es-url", required=True)
    parser.add_argument("--user", default="admin")
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

    client = Elasticsearch(args.es_url, args.user, args.password)
    for index, properties in LOOKUP_INDICES.items():
        status = migrate_index(client, index, properties)
        print(f"{index}: {status} as lookup index")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
