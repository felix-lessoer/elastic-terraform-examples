#!/usr/bin/env bash
# Ensure an Elastic Fleet cloud connector exists for AWS Managed Integrations
# (Identity Federation). Prints the connector id to stdout; optionally writes OUT_FILE.
set -euo pipefail

: "${KB_URL:?}"
: "${KB_USER:?}"
: "${KB_PASS:?}"
: "${CC_NAME:?}"
: "${ROLE_ARN:?}"

KB_URL="${KB_URL%/}"

python3 - <<'PY'
import json, os, urllib.request, base64, pathlib

kb = os.environ["KB_URL"].rstrip("/")
user, password = os.environ["KB_USER"], os.environ["KB_PASS"]
name, role_arn = os.environ["CC_NAME"], os.environ["ROLE_ARN"]
out = os.environ.get("OUT_FILE", "")

auth = base64.b64encode(f"{user}:{password}".encode()).decode()
headers = {
    "Authorization": f"Basic {auth}",
    "kbn-xsrf": "true",
    "Content-Type": "application/json",
}

def call(method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(kb + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())

items = call("GET", "/api/fleet/cloud_connectors").get("items") or []
match = next((i for i in items if i.get("name") == name), None)
if match:
    connector_id = match["id"]
else:
    created = call(
        "POST",
        "/api/fleet/cloud_connectors",
        {
            "name": name,
            "cloudProvider": "aws",
            "vars": {"role_arn": {"type": "text", "value": role_arn}},
        },
    )
    connector_id = created["item"]["id"]

print(connector_id)
if out:
    path = pathlib.Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(connector_id)
PY
