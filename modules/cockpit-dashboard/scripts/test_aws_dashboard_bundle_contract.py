import json
from pathlib import Path
import unittest


NDJSON = (
    Path(__file__).resolve().parents[1]
    / "aws-security-observability-dashboards.ndjson"
)

EXPECTED_DASHBOARDS = {
    "ecs-aws-client-vpn",
    "ecs-aws-cloudfront",
    "ecs-aws-cloudhsm",
    "ecs-aws-cloudtrail",
    "ecs-aws-elb",
    "ecs-aws-guardduty",
    "ecs-aws-ocsf-audit",
    "ecs-aws-ocsf-network",
    "ecs-aws-opensearch-metrics",
    "ecs-aws-rds",
    "ecs-aws-s3-access",
    "ecs-aws-security-hub",
    "ecs-aws-threat-hunting",
    "ecs-aws-vpc-flow-custom",
    "ecs-aws-vpc-flow",
    "ecs-aws-waf",
    "ecs-aws-web",
    "ecs-aws-workspaces",
}


class AwsDashboardBundleContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.objects = [
            json.loads(line)
            for line in NDJSON.read_text().splitlines()
            if line.strip()
        ]

    def test_bundle_contains_expected_unique_dashboards(self):
        self.assertEqual(len(self.objects), len(EXPECTED_DASHBOARDS))
        self.assertEqual(
            {item.get("id") for item in self.objects},
            EXPECTED_DASHBOARDS,
        )
        self.assertTrue(
            all(item.get("type") == "dashboard" for item in self.objects)
        )

    def test_bundle_has_no_unresolved_saved_object_references(self):
        exported = {
            (item.get("type"), item.get("id")) for item in self.objects
        }
        unresolved = [
            (reference.get("type"), reference.get("id"))
            for item in self.objects
            for reference in item.get("references", [])
            if (reference.get("type"), reference.get("id")) not in exported
        ]
        self.assertEqual(unresolved, [])

    def test_each_dashboard_has_a_title_and_panels(self):
        for item in self.objects:
            with self.subTest(dashboard=item["id"]):
                attributes = item.get("attributes", {})
                self.assertTrue(attributes.get("title"))
                self.assertTrue(json.loads(attributes.get("panelsJSON", "[]")))


if __name__ == "__main__":
    unittest.main()
