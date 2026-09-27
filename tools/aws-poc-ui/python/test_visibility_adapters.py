import unittest

from visibility_adapters import eks_manifest, eks_resources, parse_arn


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

    def test_eks_api_resources_keep_credentials_in_a_secret(self):
        resources = eks_resources(
            "elastic-poc-canary",
            "https://example.apm.aws.elastic.cloud",
            "encoded-test-key",
        )
        by_kind = {resource["kind"]: resource for _, resource in resources}
        self.assertIn("Secret", by_kind)
        self.assertNotIn(
            "encoded-test-key",
            str(by_kind["Deployment"]),
        )
        self.assertEqual(
            by_kind["Secret"]["data"]["api-key"],
            "ZW5jb2RlZC10ZXN0LWtleQ==",
        )


if __name__ == "__main__":
    unittest.main()
