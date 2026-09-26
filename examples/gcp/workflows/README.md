# Pinned Kibana Workflow YAML definitions.
#
# Export from a live project:
#   ../../scripts/export-kibana-workflows.sh \
#     --kibana "$OBS_KIBANA" --user admin --password "$OBS_PASSWORD" \
#     --out .
#
# Each *.yaml / *.yml file is deployed by module.workflows with
# workflow_id = filename (without extension), then optionally executed once
# on terraform apply (greenfield smoke run).
