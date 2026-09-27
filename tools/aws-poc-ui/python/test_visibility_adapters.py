import unittest
from unittest.mock import MagicMock, patch

from visibility_adapters import (
    eks_manifest,
    eks_principal_arn,
    eks_resources,
    elastic_request,
    parse_arn,
)


class VisibilityAdapterTest(unittest.TestCase):
    @patch("visibility_adapters.aws")
    def test_normalizes_assumed_role_for_eks_access_entry(self, aws):
        aws.return_value = {
            "Arn": (
                "arn:aws:sts::123456789012:"
                "assumed-role/platform-admin/session-name"
            )
        }
        self.assertEqual(
            eks_principal_arn("eu-west-1"),
            "arn:aws:iam::123456789012:role/platform-admin",
        )

    @patch("visibility_adapters.urllib.request.urlopen")
    def test_elasticsearch_get_request_has_no_body(self, urlopen):
        response = MagicMock()
        response.read.return_value = b"{}"
        urlopen.return_value.__enter__.return_value = response
        with patch.dict(
            "os.environ",
            {
                "ELASTICSEARCH_URL": "https://example.test",
                "ELASTICSEARCH_USERNAME": "elastic",
                "ELASTICSEARCH_PASSWORD": "secret",
            },
        ):
            elastic_request("GET", "/_security/api_key")
        request = urlopen.call_args.args[0]
        self.assertIsNone(request.data)

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
