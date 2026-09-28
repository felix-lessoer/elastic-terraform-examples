#!/usr/bin/env python3
"""Set the space-scoped Kibana default route without discarding other settings."""

from __future__ import annotations

import argparse
import json
import sys
from base64 import b64encode
from urllib import error, parse, request


def api(
    method: str,
    url: str,
    user: str,
    password: str,
    body: dict | None = None,
) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode()
    headers = {
        "Authorization": "Basic "
        + b64encode(f"{user}:{password}".encode()).decode(),
        "Content-Type": "application/json",
        "kbn-xsrf": "aws-cockpit",
    }
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=60) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else {}
    except error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"message": raw}
        return exc.code, payload


def config_url(kibana_url: str, space_id: str, version: str) -> str:
    base = kibana_url.rstrip("/")
    space = (
        ""
        if space_id == "default"
        else f"/s/{parse.quote(space_id, safe='')}"
    )
    return f"{base}{space}/api/saved_objects/config/{parse.quote(version, safe='')}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kibana-url", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--dashboard-id", required=True)
    parser.add_argument("--space-id", default="default")
    args = parser.parse_args()

    status_code, status = api(
        "GET",
        f"{args.kibana_url.rstrip('/')}/api/status",
        args.user,
        args.password,
    )
    version = (status.get("version") or {}).get("number")
    if status_code != 200 or not version:
        print(
            "Kibana default route was not changed: the project did not expose "
            "its Kibana version. Use the cockpit dashboard URL as the entry point.",
            file=sys.stderr,
        )
        return 0

    url = config_url(args.kibana_url, args.space_id, version)
    get_code, existing = api("GET", url, args.user, args.password)
    if get_code not in (200, 404):
        print(
            "Kibana default route was not changed: Advanced Settings are not "
            "available through this project API. Use the cockpit dashboard URL.",
            file=sys.stderr,
        )
        return 0

    attributes = dict(existing.get("attributes") or {}) if get_code == 200 else {}
    route = f"/app/dashboards#/view/{args.dashboard_id}"
    attributes["defaultRoute"] = route
    put_code, response = api(
        "PUT",
        f"{url}?overwrite=true",
        args.user,
        args.password,
        {"attributes": attributes},
    )
    if put_code not in (200, 201):
        message = response.get("message") or f"HTTP {put_code}"
        print(
            "Kibana default route was not changed: "
            f"{message}. Use the cockpit dashboard URL as the entry point.",
            file=sys.stderr,
        )
        return 0

    print(f"Kibana default route set to {route}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
