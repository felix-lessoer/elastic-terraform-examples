#!/usr/bin/env python3
"""Terraform external data source: ensure AWS Fleet cloud connector, return {id}."""

from __future__ import annotations

import base64
import json
import sys
import urllib.request


def main() -> int:
    query = json.load(sys.stdin)
    kb = query["kb_url"].rstrip("/")
    user, password = query["kb_user"], query["kb_pass"]
    name, role_arn = query["name"], query["role_arn"]

    auth = base64.b64encode(f"{user}:{password}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "kbn-xsrf": "true",
        "Content-Type": "application/json",
    }

    def call(method: str, path: str, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(kb + path, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())

    items = call("GET", "/api/fleet/cloud_connectors").get("items") or []
    match = next((i for i in items if i.get("name") == name), None)
    if match is None:
        # Prefer reusing any connector already pointing at this role.
        match = next(
            (
                i
                for i in items
                if ((i.get("vars") or {}).get("role_arn") or {}).get("value") == role_arn
            ),
            None,
        )
    if match is None:
        created = call(
            "POST",
            "/api/fleet/cloud_connectors",
            {
                "name": name,
                "cloudProvider": "aws",
                "vars": {"role_arn": {"type": "text", "value": role_arn}},
            },
        )
        match = created["item"]

    # external data source values must be strings
    json.dump({"id": match["id"], "name": match.get("name") or name}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
