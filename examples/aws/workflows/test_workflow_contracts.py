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

    def test_service_insight_workflows_cover_the_managed_metric_families(self):
        expected = {
            "aws-cockpit-ec2-recommendations",
            "aws-cockpit-s3-recommendations",
            "aws-cockpit-lambda-insights",
            "aws-cockpit-rds-insights",
            "aws-cockpit-elb-insights",
            "aws-cockpit-dynamodb-insights",
            "aws-cockpit-ecs-insights",
            "aws-cockpit-ebs-insights",
        }
        actual = {
            workflow["id"] for workflow in self.workflows.values()
        }
        self.assertTrue(expected.issubset(actual))

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
        workflow = self.workflows["aws-cockpit-ec2-recommendations.yaml"]
        source = (DIRECTORY / "aws-cockpit-ec2-recommendations.yaml").read_text()
        self.assertIn(
            "max_status_failed > 0 OR avg_cpu < 5 OR avg_cpu > 85",
            source,
        )
        self.assertIn("| LIMIT 200", source)
        process = next(
            step for step in workflow["steps"]
            if step["name"] == "process_metrics"
        )
        self.assertEqual(
            {step["name"] for step in process["steps"]},
            {
                "check_status_failed",
                "check_underutilized_cpu",
                "check_near_capacity_cpu",
            },
        )

    def test_unused_resource_detections_require_observed_activity_metrics(self):
        metric_workflows = (
            "aws-cockpit-ec2-recommendations.yaml",
            "aws-cockpit-lambda-insights.yaml",
            "aws-cockpit-rds-insights.yaml",
            "aws-cockpit-elb-insights.yaml",
            "aws-cockpit-dynamodb-insights.yaml",
            "aws-cockpit-ecs-insights.yaml",
            "aws-cockpit-ebs-insights.yaml",
        )
        for name in metric_workflows:
            with self.subTest(workflow=name):
                source = (DIRECTORY / name).read_text()
                self.assertIn("category: unused_resource", source)
                self.assertIn("activity_status: potentially_unused", source)
                self.assertIn("lookback_days: 14", source)
                self.assertIn("IS NOT NULL", source)

        s3_source = (
            DIRECTORY / "aws-cockpit-s3-recommendations.yaml"
        ).read_text()
        self.assertIn("category: unused_resource", s3_source)
        self.assertIn("activity_status: potentially_unused", s3_source)
        self.assertIn("lookback_days: 7", s3_source)

    def test_reference_documents_expose_lookup_join_keys(self):
        recommendation_workflows = (
            "aws-cockpit-ec2-recommendations.yaml",
            "aws-cockpit-s3-recommendations.yaml",
            "aws-cockpit-lambda-insights.yaml",
            "aws-cockpit-rds-insights.yaml",
            "aws-cockpit-elb-insights.yaml",
            "aws-cockpit-dynamodb-insights.yaml",
            "aws-cockpit-ecs-insights.yaml",
            "aws-cockpit-ebs-insights.yaml",
        )
        for name in recommendation_workflows:
            with self.subTest(workflow=name):
                source = (DIRECTORY / name).read_text()
                self.assertIn("key: \"{{ foreach.item.region }}:", source)

        assets = (DIRECTORY / "aws-cockpit-assets.yaml").read_text()
        self.assertIn("resource.key", assets)
        self.assertIn('key: "{{ foreach.item.resource_key }}"', assets)
        coverage = (DIRECTORY / "aws-cockpit-coverage.yaml").read_text()
        self.assertIn('key: "{{ foreach.item.dataset }}"', coverage)
        summary = (
            DIRECTORY / "aws-cockpit-insight-engine-summary.yaml"
        ).read_text()
        self.assertIn("key: latest", summary)


if __name__ == "__main__":
    unittest.main()
