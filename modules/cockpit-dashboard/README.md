# Cockpit dashboard (Observability hub)

Imports a pinned Kibana NDJSON export so Terraform owns the live cockpit layout
(KPIs, data-flow, ML/AI inventory, cloud asset inventory, recommendations).

| Cloud | NDJSON | Dashboard ID | Notes |
| --- | --- | --- | --- |
| GCP | `cockpit.ndjson` | `fcf1246c-6ee2-4c91-94f8-f034e8d345bc` | Latest Observability export |
| AWS | `cockpit-aws.ndjson` | `752a1ac0-26e4-49d8-a2b4-5483068809b9` | Latest Observability export |
| Azure | `cockpit-azure.ndjson` | `b8e4c2f1-9a7d-4e3b-8c5a-1d6f0e9b2a47` | Built from the GCP/AWS cockpit template |

Panels use Kibana `vis` (Lens attributes with ES|QL `textBased` datasources),
`markdown`, and `custom_content`.

Each cockpit includes a `custom_content` **OOTB integration dashboard**
navigation strip (same panel type as the header banner) with curated deep-links
into the EPR dashboards that ship with the cloud integrations, plus primary
jumps to Security alerts, ML anomaly explorer, and CSPM findings.

```bash
# Regenerate / refresh the OOTB nav panels in all three NDJSON exports
python3 modules/cockpit-dashboard/scripts/inject_ootb_nav.py
```

Curated link catalogs live in `scripts/ootb_nav.py` (`OOTB` / `PRIMARY_LINKS`).
AWS and Azure rebuild scripts call `inject_ootb_nav()` automatically.

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

# Azure (rebuild from the GCP template)
python3 modules/cockpit-dashboard/scripts/build_azure_cockpit_ndjson.py /tmp/gcp-cockpit-live.ndjson

cd examples/<cloud> && terraform apply -target=module.cockpit
```

`overwrite = true` re-applies the file on every apply so Kibana stays aligned with the export.

CPS cross-cluster references in the NDJSON use the live Security project alias
when ES|QL can resolve it (e.g. `gcp-observe-and-protect-…`). On AWS, the
Observability cockpit uses an **insight fabric** of local indices so panels never
depend on broken CPS qualifiers (`no_matching_project_exception` even when the
Cloud link is `enabled`). Security deep-links remain in the OOTB nav.

## Multi-cloud insight fabric (Datadog-comparable)

Shared helpers live in `scripts/insight_fabric_common.py`. Each cloud has a
seeder + panel injector + assets/coverage workflows.

| Cloud | Seeder | Inject | Indices |
| --- | --- | --- | --- |
| AWS | `seed_aws_insight_indices.py` | `inject_aws_insight_panels.py` | `aws-cockpit-{security-kpi,coverage,assets,events,health,recommendations}` |
| GCP | `seed_gcp_insight_indices.py` | `inject_gcp_insight_panels.py` | `gcp-cockpit-{security-kpi,coverage,assets,events,recommendations}` |
| Azure | `seed_azure_insight_indices.py` | `inject_azure_insight_panels.py` | `azure-cockpit-{security-kpi,coverage,assets,events,recommendations}` |

```bash
# Refresh insight panels in the NDJSON exports
python3 modules/cockpit-dashboard/scripts/inject_aws_insight_panels.py
python3 modules/cockpit-dashboard/scripts/inject_gcp_insight_panels.py
python3 modules/cockpit-dashboard/scripts/inject_azure_insight_panels.py

# Seed Observability indices from Security + Observability Elasticsearch
python3 modules/cockpit-dashboard/scripts/seed_<cloud>_insight_indices.py \
  --obs-es "$OBS_ES" --sec-es "$SEC_ES" \
  --obs-password "$OBS_PASSWORD" --sec-password "$SEC_PASSWORD"
```

Each `examples/{aws,gcp,azure}` wires the seeder as
`terraform_data.seed_<cloud>_insight_indices` (runs after cockpit + workflows).

## Recommendations index

Recommendation documents are produced by pinned Kibana Workflows under
`examples/{gcp,aws,azure}/workflows/` (see those READMEs), not by this module.

| Cloud | Index | Seeded by workflows |
| --- | --- | --- |
| GCP | `gcp-cockpit-recommendations` | Cloud Run, Cloud SQL, GKE, Host |
| AWS | `aws-cockpit-recommendations` | EC2, S3 |
| Azure | `azure-cockpit-recommendations` | VM, Storage |

Optional Python seeds for offline backfill:
`scripts/generate_aws_recommendations.py`,
`scripts/generate_azure_recommendations.py`,
`scripts/seed_aws_insight_indices.py`.
