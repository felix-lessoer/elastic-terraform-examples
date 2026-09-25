# Cockpit dashboard (Observability hub)

Imports a pinned Kibana NDJSON export so Terraform owns the live cockpit layout
(KPIs, data-flow, ML/AI inventory, cloud asset inventory, recommendations).

| Cloud | NDJSON | Notes |
| --- | --- | --- |
| GCP | `cockpit.ndjson` | Export from Observability Kibana |
| AWS | `cockpit-aws.ndjson` | Built from the live GCP cockpit concept (`fcf1246c-…`) plus AWS metrics inventory + `aws-cockpit-recommendations` |

Panels use Kibana `vis` (Lens attributes with ES|QL `textBased` datasources) and `markdown`.

## AWS: refresh from the GCP cockpit concept

```bash
# 1) Export the latest GCP cockpit (Observability)
curl -u admin:"$GCP_OBS_PASSWORD" -H 'kbn-xsrf: true' -H 'content-type: application/json' \
  -X POST "$GCP_OBS_KIBANA/api/saved_objects/_export" \
  -d '{"objects":[{"type":"dashboard","id":"fcf1246c-6ee2-4c91-94f8-f034e8d345bc"}],"includeReferencesDeep":true,"excludeExportDetails":true}' \
  -o /tmp/gcp-cockpit-live.ndjson

# 2) Rebuild AWS NDJSON (CSPM inventory on misconfiguration_latest + live metrics + recommendations)
python3 modules/cockpit-dashboard/scripts/build_aws_cockpit_ndjson.py /tmp/gcp-cockpit-live.ndjson

# 3) Seed recommendations index from live AWS metrics
python3 modules/cockpit-dashboard/scripts/generate_aws_recommendations.py \
  --es-url "$AWS_OBS_ES" --password "$AWS_OBS_PASSWORD"

# 4) Apply
cd examples/aws && terraform apply -target=module.cockpit
```

`overwrite = true` re-applies the file on every apply so Kibana stays aligned with the export.

## Recommendations index

`aws-cockpit-recommendations` mirrors GCP's `gcp-cockpit-recommendations`:

| Category | Trigger |
| --- | --- |
| `cost_optimization` | EC2 avg CPU &lt; 5% / 24h, empty S3 buckets |
| `performance_risk` | EC2 avg CPU &gt; 85% / 24h, failed status checks |
