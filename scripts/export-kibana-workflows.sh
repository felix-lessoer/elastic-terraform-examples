#!/usr/bin/env bash
# Export Kibana Workflows YAML into a directory for Terraform pinning.
# Usage:
#   ./scripts/export-kibana-workflows.sh --kibana URL --user admin --password PASS --out DIR
set -euo pipefail

KIBANA=""
USER="admin"
PASSWORD=""
OUT=""
API_VERSION="2023-10-31"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --kibana) KIBANA="$2"; shift 2 ;;
    --user) USER="$2"; shift 2 ;;
    --password) PASSWORD="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --api-version) API_VERSION="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

[[ -n "$KIBANA" && -n "$PASSWORD" && -n "$OUT" ]] || {
  echo "required: --kibana --password --out" >&2
  exit 2
}

KIBANA="${KIBANA%/}"
mkdir -p "$OUT"
tmp=$(mktemp)

curl -sk -u "${USER}:${PASSWORD}" \
  "${KIBANA}/api/workflows?page=1&size=100" \
  -H "kbn-xsrf: true" \
  -H "x-elastic-internal-origin: Kibana" \
  -H "elastic-api-version: ${API_VERSION}" \
  -o "$tmp"

python3 - "$OUT" "$tmp" <<'PY'
import json, os, re, sys
out, path = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as f:
    data = json.load(f)
total = data.get("total", 0)
print(f"found {total} workflow(s)")
for w in data.get("results", []):
    wid = w.get("id") or "workflow"
    yaml_body = w.get("yaml") or ""
    if not re.search(r"(?m)^id:\s*", yaml_body):
        yaml_body = f"id: {wid}\n" + yaml_body
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", wid).strip("-").lower()
    dest = os.path.join(out, f"{safe}.yaml")
    with open(dest, "w", encoding="utf-8") as f:
        f.write(yaml_body if yaml_body.endswith("\n") else yaml_body + "\n")
    print(f"wrote {dest} ({w.get('name')})")
PY
rm -f "$tmp"
