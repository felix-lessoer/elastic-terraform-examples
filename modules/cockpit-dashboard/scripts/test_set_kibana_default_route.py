import unittest

from set_kibana_default_route import config_url


class KibanaDefaultRouteTests(unittest.TestCase):
    def test_default_space_uses_unprefixed_saved_object_api(self):
        self.assertEqual(
            config_url("https://example.kb.elastic.cloud/", "default", "9.4.0"),
            "https://example.kb.elastic.cloud/api/saved_objects/config/9.4.0",
        )

    def test_named_space_is_url_encoded(self):
        self.assertEqual(
            config_url("https://example.kb.elastic.cloud", "customer poc", "9.4.0"),
            "https://example.kb.elastic.cloud/s/customer%20poc/api/saved_objects/config/9.4.0",
        )


if __name__ == "__main__":
    unittest.main()
