from pathlib import Path
import unittest

import yaml


DIRECTORY = Path(__file__).resolve().parent


class AwsWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflows = {
            path.name: yaml.safe_load(path.read_text())
            for path in DIRECTORY.glob("*.yaml")
        }

    def test_workflow_ids_are_unique_and_runnable(self):
        identifiers = [
            workflow["id"] for workflow in self.workflows.values()
        ]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        for workflow in self.workflows.values():
            trigger_types = {
                trigger["type"] for trigger in workflow["triggers"]
            }
            self.assertIn("manual", trigger_types)
            self.assertTrue(workflow["steps"])

    def test_structured_outputs_remain_expressions(self):
        for workflow in self.workflows.values():
            for step in workflow["steps"]:
                if step.get("type") in {"data.map", "foreach"}:
                    value = step.get("items") or step.get("foreach")
                    self.assertTrue(value.startswith("${{"))
                    self.assertTrue(value.endswith("}}"))

    def test_recommendation_workflows_replace_snapshots(self):
        for name in (
            "aws-cockpit-ec2-recommendations.yaml",
            "aws-cockpit-s3-recommendations.yaml",
        ):
            workflow = self.workflows[name]
            cleanup = workflow["steps"][0]
            self.assertEqual(cleanup["type"], "elasticsearch.request")
            self.assertIn("_delete_by_query", cleanup["with"]["path"])
            source = (DIRECTORY / name).read_text()
            self.assertNotIn("%Y%m%dT%H%M", source)

    def test_ec2_fanout_is_limited_to_actionable_resources(self):
        source = (
            DIRECTORY / "aws-cockpit-ec2-recommendations.yaml"
        ).read_text()
        self.assertIn(
            "max_status_failed > 0 OR avg_cpu < 5 OR avg_cpu > 85",
            source,
        )
        self.assertIn("| LIMIT 200", source)


if __name__ == "__main__":
    unittest.main()
