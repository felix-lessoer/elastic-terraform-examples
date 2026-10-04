import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from inject_gcp_insight_panels import scrub


DASHBOARD_ID = "fcf1246c-6ee2-4c91-94f8-f034e8d345bc"
NDJSON = Path(__file__).resolve().parents[1] / "cockpit.ndjson"


class GcpCockpitSavedObjectContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.objects = [
            json.loads(line) for line in NDJSON.read_text().splitlines() if line.strip()
        ]
        cls.dashboard = next(
            item
            for item in cls.objects
            if item.get("type") == "dashboard" and item.get("id") == DASHBOARD_ID
        )
        cls.panels = json.loads(cls.dashboard["attributes"]["panelsJSON"])
        cls.serialized_panels = json.dumps(cls.panels)

    def test_export_contains_only_the_expected_dashboard(self):
        dashboards = [
            item for item in self.objects if item.get("type") == "dashboard"
        ]
        self.assertEqual([item["id"] for item in dashboards], [DASHBOARD_ID])

    def test_saved_object_references_are_not_dangling(self):
        exported = {(item.get("type"), item.get("id")) for item in self.objects}
        for item in self.objects:
            for reference in item.get("references", []):
                self.assertIn((reference["type"], reference["id"]), exported)

    def test_dashboard_represents_all_three_insight_levels(self):
        description = self.dashboard["attributes"]["description"].lower()
        for level in ("raw", "deterministic", "summary"):
            self.assertIn(level, description)
        self.assertTrue(
            "metrics-gcp." in self.serialized_panels
            or "logs-gcp." in self.serialized_panels
        )
        self.assertIn("gcp-cockpit-recommendations", self.serialized_panels)
        self.assertIn("FROM gcp-cockpit-insight-summary", self.serialized_panels)

    def test_summary_uses_the_latest_document(self):
        panel = next(
            panel
            for panel in self.panels
            if "FROM gcp-cockpit-insight-summary" in json.dumps(panel)
        )
        query = json.dumps(panel)
        self.assertIn("SORT @timestamp DESC", query)
        self.assertIn("LIMIT 1", query)

    def test_cps_alias_scrubbing_is_configuration_driven(self):
        alias = "customer-security-project-a1b2c3"
        panel = {
            "embeddableConfig": {
                "query": (
                    f'FROM "{alias}:'
                    'security_solution-cloud_security_posture.misconfiguration_latest"'
                )
            }
        }
        scrubbed = json.dumps(scrub(panel, (alias,)))
        self.assertNotIn(alias, scrubbed)
        self.assertIn("security_solution-*.misconfiguration_latest", scrubbed)

    def test_default_route_config_is_not_bundled_with_dashboard_export(self):
        # Terraform round-trips the versioned config object separately so this
        # dashboard export cannot overwrite unrelated space settings.
        configs = [item for item in self.objects if item.get("type") == "config"]
        self.assertEqual(configs, [])


if __name__ == "__main__":
    unittest.main()
