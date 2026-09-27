import unittest

from visibility_adapters import eks_manifest, parse_arn


class VisibilityAdapterTest(unittest.TestCase):
    def test_parses_region_and_resource_from_arn(self):
        self.assertEqual(
            parse_arn("arn:aws:lambda:eu-west-1:123:function:checkout"),
            ("eu-west-1", "function:checkout"),
        )

    def test_eks_manifest_keeps_credentials_in_a_secret(self):
        manifest = eks_manifest(
            "elastic-poc-canary",
            "https://example.apm.aws.elastic.cloud",
            "encoded-test-key",
        )
        self.assertIn("kind: Secret", manifest)
        self.assertIn('api-key: "encoded-test-key"', manifest)
        self.assertIn("secretKeyRef:", manifest)
        self.assertNotIn("value: encoded-test-key", manifest)


if __name__ == "__main__":
    unittest.main()
