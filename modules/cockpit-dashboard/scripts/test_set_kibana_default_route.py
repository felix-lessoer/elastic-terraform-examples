import unittest

from set_kibana_default_route import space_api_url, with_default_route


class KibanaDefaultRouteTests(unittest.TestCase):
    def test_default_space_uses_unprefixed_api(self):
        self.assertEqual(
            space_api_url(
                "https://example.kb.elastic.cloud/",
                "default",
                "/api/saved_objects/_export",
            ),
            "https://example.kb.elastic.cloud/api/saved_objects/_export",
        )

    def test_named_space_is_url_encoded(self):
        self.assertEqual(
            space_api_url(
                "https://example.kb.elastic.cloud",
                "customer poc",
                "/api/saved_objects/_export",
            ),
            "https://example.kb.elastic.cloud/s/customer%20poc/api/saved_objects/_export",
        )

    def test_default_route_preserves_other_advanced_settings(self):
        original = {
            "type": "config",
            "id": "9.6.0",
            "attributes": {
                "buildNum": 111602,
                "defaultIndex": "metrics-*",
                "isDefaultIndexMigrated": True,
            },
            "references": [],
        }
        updated, route = with_default_route(original, "cockpit-id")

        self.assertEqual(
            route,
            "/app/dashboards#/view/cockpit-id?_g=(filters:!())",
        )
        self.assertEqual(updated["attributes"]["defaultIndex"], "metrics-*")
        self.assertEqual(updated["attributes"]["buildNum"], 111602)
        self.assertEqual(updated["attributes"]["defaultRoute"], route)
        self.assertNotIn("defaultRoute", original["attributes"])


if __name__ == "__main__":
    unittest.main()
