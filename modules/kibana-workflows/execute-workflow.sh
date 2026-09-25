#!/usr/bin/env bash
# Execute a Kibana workflow once (used by terraform_data local-exec).
set -euo pipefail

: "${WF_ID:?}"
: "${KIBANA_URL:?}"
: "${KIBANA_USER:?}"
: "${KIBANA_PASS:?}"
WF_ENABLED="${WF_ENABLED:-true}"
WF_VALID="${WF_VALID:-true}"

if [[ "$WF_VALID" != "true" ]]; then
  echo "skip execute $WF_ID: invalid configuration"
  exit 0
fi
if [[ "$WF_ENABLED" != "true" ]]; then
  echo "skip execute $WF_ID: disabled"
  exit 0
fi

out="/tmp/wf-run-${WF_ID}.json"
code=$(curl -sk -u "${KIBANA_USER}:${KIBANA_PASS}" \
  -o "$out" -w "%{http_code}" \
  -X POST "${KIBANA_URL}/api/workflows/workflow/${WF_ID}/run" \
  -H "kbn-xsrf: true" \
  -H "Content-Type: application/json" \
  -H "x-elastic-internal-origin: Kibana" \
  -H "elastic-api-version: 2023-10-31" \
  -d '{}')

echo "execute ${WF_ID} http=${code}"
cat "$out"
echo
[[ "$code" =~ ^2 ]]
