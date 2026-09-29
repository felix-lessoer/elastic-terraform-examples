import json
from pathlib import Path
import unittest


DASHBOARD_ID = "752a1ac0-26e4-49d8-a2b4-5483068809b9"
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
        self.assertEqual(len(self.objects), 1)
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
            if panel.get("panelIndex")
            == "c0ffee10-26e4-49d8-a2b4-548306880910"
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
