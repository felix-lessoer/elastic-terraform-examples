# Kibana workflows

Deploys Elastic Kibana Workflows (YAML) via
`elasticstack_kibana_agentbuilder_workflow`, then optionally executes each
enabled workflow once on apply (greenfield smoke run).

## Pin workflows from a live Kibana

```bash
# From repo root — exports YAML into examples/gcp/workflows/
./scripts/export-kibana-workflows.sh \
  --kibana "$OBS_KIBANA" \
  --user admin \
  --password "$OBS_PASSWORD" \
  --out examples/gcp/workflows
```

Filenames become stable `workflow_id`s across destroy/apply.

## Layout

```
examples/gcp/workflows/
  my-workflow.yaml   # deployed as workflow_id=my-workflow
```
