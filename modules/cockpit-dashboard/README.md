# Cockpit dashboard (Observability hub)

Imports a pinned Kibana NDJSON export so Terraform owns the live cockpit layout
(KPIs, data-flow, ML/AI inventory, cloud asset inventory, recommendations).

| Cloud | NDJSON | Dashboard ID | Notes |
| --- | --- | --- | --- |
| GCP | `cockpit.ndjson` | `fcf1246c-6ee2-4c91-94f8-f034e8d345bc` | Latest Observability export |
| AWS | `cockpit-aws.ndjson` | `752a1ac0-26e4-49d8-a2b4-5483068809b9` | Latest Observability export |

Panels use Kibana `vis` (Lens attributes with ES|QL `textBased` datasources),
`markdown`, and `custom_content`.

## Refresh from a live Observability Kibana

```bash
# GCP
curl -u admin:"$GCP_OBS_PASSWORD" -H 'kbn-xsrf: true' -H 'content-type: application/json' \
  -X POST "$GCP_OBS_KIBANA/api/saved_objects/_export" \
  -d '{"objects":[{"type":"dashboard","id":"fcf1246c-6ee2-4c91-94f8-f034e8d345bc"}],"includeReferencesDeep":true,"excludeExportDetails":true}' \
  -o modules/cockpit-dashboard/cockpit.ndjson

# AWS
curl -u admin:"$AWS_OBS_PASSWORD" -H 'kbn-xsrf: true' -H 'content-type: application/json' \
  -X POST "$AWS_OBS_KIBANA/api/saved_objects/_export" \
  -d '{"objects":[{"type":"dashboard","id":"752a1ac0-26e4-49d8-a2b4-5483068809b9"}],"includeReferencesDeep":true,"excludeExportDetails":true}' \
  -o modules/cockpit-dashboard/cockpit-aws.ndjson

cd examples/<cloud> && terraform apply -target=module.cockpit
```

`overwrite = true` re-applies the file on every apply so Kibana stays aligned with the export.

CPS cross-cluster references in the NDJSON use the live Security project alias
(e.g. `gcp-observe-and-protect-…` / `aws-observe-and-protect-…`). After a
greenfield recreate with a new project name, re-export from the live UI or
search-replace the alias before apply.

## Recommendations index

Recommendation documents are produced by pinned Kibana Workflows under
`examples/{gcp,aws}/workflows/` (see those READMEs), not by this module.

| Cloud | Index | Seeded by workflows |
| --- | --- | --- |
| GCP | `gcp-cockpit-recommendations` | Cloud Run, Cloud SQL, GKE, Host |
| AWS | `aws-cockpit-recommendations` | EC2, S3 |

Optional Python seed for AWS still exists at
`scripts/generate_aws_recommendations.py` for offline backfill.
