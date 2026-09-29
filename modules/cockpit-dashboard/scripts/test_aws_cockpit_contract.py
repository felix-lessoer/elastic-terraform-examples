import json
from pathlib import Path
import unittest


DASHBOARD_ID = "45f84000-d68b-4bb1-9df2-09223fba6b29"
NDJSON = Path(__file__).resolve().parents[1] / "cockpit-aws.ndjson"


class AwsCockpitSavedObjectContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.objects = [
            json.loads(line)
            for line in NDJSON.read_text().splitlines()
            if line.strip()
        ]
        cls.dashboard = next(
            item
            for item in cls.objects
            if item.get("type") == "dashboard"
            and item.get("id") == DASHBOARD_ID
        )
        cls.panels = json.loads(
            cls.dashboard["attributes"]["panelsJSON"]
        )

    def test_export_contains_the_terraform_owned_dashboard(self):
        dashboards = [
            item for item in self.objects if item.get("type") == "dashboard"
        ]
        self.assertEqual(len(dashboards), 1)
        exported_references = {
            (item.get("type"), item.get("id")) for item in self.objects
        }
        for reference in self.dashboard.get("references", []):
            self.assertIn(
                (reference["type"], reference["id"]),
                exported_references,
            )
        self.assertIn(
            "Insight Engine",
            self.dashboard["attributes"]["description"],
        )

    def test_insight_visualizations_are_esql_lens_panels(self):
        insight_panels = [
            panel
            for panel in self.panels
            if "aws-cockpit-" in json.dumps(panel)
            and panel.get("type") == "vis"
        ]
        self.assertGreaterEqual(len(insight_panels), 10)
        for panel in insight_panels:
            state = panel["embeddableConfig"]["attributes"]["state"]
            self.assertIn("textBased", state["datasourceStates"])

    def test_agent_summary_is_prominent_and_uses_latest_document(self):
        panel = next(
            panel
            for panel in self.panels
            if "FROM aws-cockpit-insight-summary"
            in json.dumps(panel)
            and "KEEP @timestamp, priority, headline"
            in json.dumps(panel)
        )
        query = json.dumps(panel)
        self.assertIn("aws-cockpit-insight-summary", query)
        self.assertIn("SORT @timestamp DESC", query)
        self.assertIn("LIMIT 1", query)

    def test_custom_content_is_not_used_for_navigation(self):
        custom_panels = [
            panel
            for panel in self.panels
            if panel.get("type") == "custom_content"
        ]
        for panel in custom_panels:
            template = panel["embeddableConfig"].get("template", "")
            self.assertNotIn("href=", template)


if __name__ == "__main__":
    unittest.main()
