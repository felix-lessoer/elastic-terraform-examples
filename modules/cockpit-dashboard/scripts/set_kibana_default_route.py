#!/usr/bin/env python3
"""Set defaultRoute by round-tripping Kibana's versioned config saved object."""

from __future__ import annotations

import argparse
import json
import secrets
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


def space_api_url(kibana_url: str, space_id: str, path: str) -> str:
    base = kibana_url.rstrip("/")
    space = (
        ""
        if space_id == "default"
        else f"/s/{parse.quote(space_id, safe='')}"
    )
    return f"{base}{space}{path}"


def with_default_route(config: dict, dashboard_id: str) -> tuple[dict, str]:
    updated = dict(config)
    attributes = dict(updated.get("attributes") or {})
    route = f"/app/dashboards#/view/{dashboard_id}?_g=(filters:!())"
    attributes["defaultRoute"] = route
    updated["attributes"] = attributes
    return updated, route


def import_saved_object(
    kibana_url: str,
    space_id: str,
    user: str,
    password: str,
    saved_object: dict,
) -> tuple[int, dict]:
    boundary = f"----aws-cockpit-{secrets.token_hex(12)}"
    ndjson = json.dumps(saved_object, separators=(",", ":")) + "\n"
    payload = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="kibana-config.ndjson"\r\n'
        "Content-Type: application/x-ndjson\r\n\r\n"
        f"{ndjson}\r\n"
        f"--{boundary}--\r\n"
    ).encode()
    headers = {
        "Authorization": "Basic "
        + b64encode(f"{user}:{password}".encode()).decode(),
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "kbn-xsrf": "aws-cockpit",
    }
    url = space_api_url(
        kibana_url,
        space_id,
        "/api/saved_objects/_import?overwrite=true",
    )
    req = request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=60) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else {}
    except error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            result = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            result = {"message": raw}
        return exc.code, result


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

    export_code, existing = api(
        "POST",
        space_api_url(
            args.kibana_url,
            args.space_id,
            "/api/saved_objects/_export",
        ),
        args.user,
        args.password,
        {
            "objects": [{"type": "config", "id": version}],
            "excludeExportDetails": True,
        },
    )
    if export_code != 200 or existing.get("type") != "config":
        message = existing.get("message") or f"HTTP {export_code}"
        raise RuntimeError(
            "Unable to export the Kibana config saved object: "
            f"{message}. Set the cockpit default route once in Advanced Settings."
        )

    updated, route = with_default_route(existing, args.dashboard_id)
    import_code, response = import_saved_object(
        args.kibana_url,
        args.space_id,
        args.user,
        args.password,
        updated,
    )
    if import_code != 200 or response.get("success") is not True:
        message = response.get("message") or f"HTTP {import_code}"
        raise RuntimeError(
            f"Unable to import the Kibana config saved object: {message}"
        )

    print(f"Kibana config saved object imported with default route {route}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
