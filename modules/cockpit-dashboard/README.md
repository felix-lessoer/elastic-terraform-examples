# Cockpit dashboard (Observability hub)

Manages the **GCP Observe & Protect Cockpit** dashboard by importing a pinned
Kibana NDJSON export (`cockpit.ndjson`). This freezes the live Kibana layout
(KPIs, data-flow charts, ML/AI inventory, GCP inventory) as Terraform source of truth.

## Refresh after editing in Kibana

```bash
# Export (exclude export details footer)
curl -u admin:"$OBS_PASSWORD" -H 'kbn-xsrf: true' -H 'content-type: application/json' \
  -X POST "$OBS_KIBANA/api/saved_objects/_export" \
  -d '{"objects":[{"type":"dashboard","id":"c51727b1-226a-4955-9cb2-fcd59f950d55"}],"includeReferencesDeep":false,"excludeExportDetails":true}' \
  -o modules/cockpit-dashboard/cockpit.ndjson

terraform apply -target=module.cockpit
```

`overwrite = true` re-applies the file on every apply so Kibana stays aligned with the export.
