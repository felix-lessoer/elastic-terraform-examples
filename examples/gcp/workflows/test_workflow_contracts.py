from pathlib import Path
import re
import unittest

import yaml


DIRECTORY = Path(__file__).resolve().parent
GCP_ROOT = DIRECTORY.parent


class GcpWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflows = {
            path.name: yaml.safe_load(path.read_text())
            for path in DIRECTORY.glob("*.yaml")
        }

    def test_workflow_ids_are_unique_runnable_and_scheduled(self):
        identifiers = [workflow["id"] for workflow in self.workflows.values()]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        for name, workflow in self.workflows.items():
            with self.subTest(workflow=name):
                trigger_types = {trigger["type"] for trigger in workflow["triggers"]}
                self.assertIn("manual", trigger_types)
                self.assertIn("scheduled", trigger_types)
                self.assertTrue(workflow["steps"])

    def test_structured_fanout_inputs_are_expressions(self):
        for name, workflow in self.workflows.items():
            for step in workflow["steps"]:
                if step.get("type") in {"data.map", "foreach"}:
                    with self.subTest(workflow=name, step=step["name"]):
                        value = step.get("items") or step.get("foreach")
                        self.assertTrue(value.startswith("${{"))
                        self.assertTrue(value.endswith("}}"))

    def test_recommendation_snapshots_are_scoped_and_deterministic(self):
        recommendation_files = (
            "gcp-cockpit-host-recommendations.yaml",
            "gcp-cockpit-gke-recommendations.yaml",
            "gcp-cockpit-cloudrun-recommendations.yaml",
            "gcp-cockpit-cloudsql-recommendations.yaml",
        )
        for name in recommendation_files:
            with self.subTest(workflow=name):
                workflow = self.workflows[name]
                cleanup = workflow["steps"][0]
                self.assertEqual(cleanup["type"], "elasticsearch.request")
                self.assertIn("_delete_by_query", cleanup["with"]["path"])
                source = (DIRECTORY / name).read_text()
                self.assertIn("resource.type", source)
                self.assertIn("resource:", source)
                self.assertIn("key:", source)
                self.assertNotRegex(source, r"%Y%m%d|date:.*%[YHMS]")

    def test_all_esql_and_fanout_are_bounded(self):
        for name, workflow in self.workflows.items():
            for step in workflow["steps"]:
                if step.get("type") == "elasticsearch.esql.query":
                    with self.subTest(workflow=name, step=step["name"]):
                        query = step["with"]["query"]
                        self.assertRegex(query, r"\|\s+LIMIT\s+\d+")
                        self.assertNotRegex(query, r"LIMIT\s+([5-9]\d\d|\d{4,})")

    def test_unused_findings_require_observed_activity(self):
        for name in (
            "gcp-cockpit-host-recommendations.yaml",
            "gcp-cockpit-gke-recommendations.yaml",
            "gcp-cockpit-cloudrun-recommendations.yaml",
        ):
            source = (DIRECTORY / name).read_text()
            with self.subTest(workflow=name):
                self.assertRegex(source, r'category:\s*["\']?unused_resource')
                self.assertIn("activity_status: potentially_unused", source)
                self.assertIn("observations", source)
                self.assertIn("IS NOT NULL", source)
                for field in (
                    "confidence:",
                    "evidence_refs:",
                    "contradictory_evidence:",
                    "missing_telemetry:",
                    "expected_value:",
                    "safe_next_action:",
                ):
                    self.assertIn(field, source)

    def test_assets_and_findings_share_stable_gcp_key_shape(self):
        assets = (DIRECTORY / "gcp-cockpit-assets.yaml").read_text()
        self.assertIn(
            "{{ foreach.item.project_id }}:{{ foreach.item.region }}:gce_instance:",
            assets,
        )
        self.assertIn(
            "{{ foreach.item.project_id }}:{{ foreach.item.region }}:gce_instance:",
            (DIRECTORY / "gcp-cockpit-host-recommendations.yaml").read_text(),
        )

    def test_telemetry_requirements_are_explicit_for_optional_streams(self):
        tools = (GCP_ROOT / "agent_workflow_tools.tf").read_text()
        expected = {
            "gcp-cockpit-gke-recommendations": "gke-gcp/metrics",
            "gcp-cockpit-cloudrun-recommendations": "cloudrun-gcp/metrics",
            "gcp-cockpit-cloudsql-recommendations": "cloudsql-gcp/metrics",
        }
        for workflow, integration in expected.items():
            self.assertRegex(
                tools,
                rf'"{re.escape(workflow)}"\s*=\s*\["{re.escape(integration)}"\]',
            )
            self.assertIn(f"Requires the {integration}", (
                DIRECTORY / f"{workflow}.yaml"
            ).read_text())

    def test_summary_and_ml_keeper_contracts(self):
        summary = self.workflows["gcp-cockpit-insight-engine-summary.yaml"]
        self.assertEqual(summary["steps"][-1]["with"]["id"], "latest")
        self.assertEqual(
            summary["steps"][-1]["with"]["document"]["lookup"]["key"], "latest"
        )
        keeper = (DIRECTORY / "gcp-ml-datafeed-keeper.yaml").read_text()
        self.assertIn("/_ml/anomaly_detectors/gcp-event-rate/_open", keeper)
        self.assertIn("/_ml/datafeeds/datafeed-gcp-event-rate/_start", keeper)

    def test_agent_tools_are_fixed_scope_bounded_and_read_only(self):
        source = (GCP_ROOT / "agent_workflow_tools.tf").read_text()
        self.assertEqual(source.count('type        = "esql"'), 1)
        self.assertNotIn('type        = "workflow"', source)
        queries = [
            line.split("=", 1)[1].strip().strip('"')
            for line in source.splitlines()
            if line.strip().startswith("query") and "FROM gcp-cockpit-" in line
        ]
        self.assertEqual(len(queries), 3)
        for query in queries:
            self.assertRegex(query, r"FROM gcp-cockpit-")
            self.assertRegex(query, r"\| LIMIT (?:1|50)")
        self.assertIn("params = {}", source)


if __name__ == "__main__":
    unittest.main()
