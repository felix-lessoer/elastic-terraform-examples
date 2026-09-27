# Azure Observe and Protect (modern PoC)

Mirrors the GCP/AWS dual-project pattern for Azure:

1. **Elastic Security** serverless (Complete) — agentless CSPM + agent Event Hub activity/platform logs + Azure detection rules
2. **Elastic Observability** serverless — CPS-linked hub with Azure Monitor metrics + billing on a dedicated Fleet policy
3. **Cockpit dashboard** on Observability — pinned NDJSON (`modules/cockpit-dashboard/cockpit-azure.ndjson`, id `b8e4c2f1-…`) with CSPM asset inventory (via CPS `misconfiguration_latest`), live Azure metrics inventory, and `azure-cockpit-recommendations`
4. **Kibana Workflows** — recommendation generators under `examples/azure/workflows/` (VM, Storage) with optional execute-on-apply

## Agentless vs agent

| Integration | Mode | Why |
| --- | --- | --- |
| CSPM (CIS Azure) | **Agentless** | `cloud_security_posture` managed integration |
| Activity / platform logs | **Agent** | Event Hub consumer on Security Fleet agent |
| Azure Monitor metrics (VM / storage / ACI) | **Agent** | `azure_metrics` on Observability Fleet agent |
| Billing / Cost Management | **Agent** | `azure_billing` on Observability Fleet agent |

Two Azure Linux VMs enroll into the Security and Observability Fleet policies. The collector app registration (created by `modules/azure-cloud`) supplies SP credentials for metrics/billing and Event Hub listen rights for logs.

## Company tags (required)

Every taggable Azure resource gets your policy tags via `company_tags`. Prefer the same keys as GCP `company_labels` / AWS `company_tags` when org policy allows.

```hcl
company_tags = {
  division    = "field"
  org         = "sa"
  cost-center = "platform"
  owner       = "sre-team"
  environment = "poc"
}
```

## Prerequisites

```bash
export EC_API_KEY="..."
# Provide Azure SP used by Terraform itself via tfvars or env:
# ARM_CLIENT_ID / ARM_CLIENT_SECRET / ARM_SUBSCRIPTION_ID / ARM_TENANT_ID
```

```bash
cd examples/azure
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform apply
```

## What to open after apply

| Surface | Where |
| --- | --- |
| Cockpit dashboard | `observability_kibana_url` / `cockpit_dashboard_url` |
| Kibana Workflows | `examples/azure/workflows/*.yaml` → `azure-cockpit-recommendations` (VM, Storage) |
| Security Fleet / CSPM | `kibana_url` — agent `${name_prefix}-agent` |
| Observability Fleet | `observability_kibana_url` — agent `${name_prefix}-obs-agent` |
| AI agents | Observability → Agent Builder (`azure-security-analyst`, `azure-obs-triage`) |

Toggle Observability hub with `enable_observability_project = false` if you only want Security.

## Refresh the Azure cockpit from the GCP/AWS template

```bash
# Export latest GCP cockpit (or use modules/cockpit-dashboard/cockpit.ndjson)
python3 - <<'PY'
import json
from pathlib import Path
src=Path('modules/cockpit-dashboard/cockpit.ndjson')
dash=next(json.loads(l) for l in src.read_text().splitlines() if '"dashboard"' in l and '"type"' in l)
# prefer explicit type check
for line in src.read_text().splitlines():
    o=json.loads(line)
    if o.get('type')=='dashboard':
        Path('/tmp/gcp-cockpit-for-azure.ndjson').write_text(json.dumps(o)+'\n')
        break
PY
python3 modules/cockpit-dashboard/scripts/build_azure_cockpit_ndjson.py /tmp/gcp-cockpit-for-azure.ndjson
cd examples/azure && terraform apply -target=module.cockpit
```

After the first greenfield apply, replace the CPS alias `azure-observe-and-protect-azure0` in the NDJSON with the live Security project alias if it differs, then re-apply.
