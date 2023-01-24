#!/bin/bash

eval "$(jq -r '@sh "ELASTIC_ENDPOINT=\(.elastic_endpoint) ELASTIC_USERNAME=\(.elastic_username) ELASTIC_PASSWORD=\(.elastic_password) ELASTIC_JSON_BODY=\(.elastic_json_body) ELASTIC_INDEX_NAME=\(.elastic_index_name)"')"

output=$(curl -s -X POST -u "$ELASTIC_USERNAME:$ELASTIC_PASSWORD" \
   -H 'Content-Type:application/json' -d "${ELASTIC_JSON_BODY}" \
   ${ELASTIC_ENDPOINT}/${ELASTIC_INDEX_NAME}/_bulk | jq '.')

ITEMS=$( echo $output | jq -r '.items' )
ERROR=$( echo $output | jq -r '.error' )
jq -n --arg items "$ITEMS" --arg error "$ERROR" '{"items" : $items, "error" : $error}'
