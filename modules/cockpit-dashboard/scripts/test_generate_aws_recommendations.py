import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import generate_aws_recommendations as recommendations
from seed_aws_insight_indices import aws_s3_asset_docs, manifest_asset_docs


class EsqlTests(unittest.TestCase):
    def test_existing_recommendation_index_gets_timestamp_mapping(self):
        existing = RuntimeError(
            "resource_already_exists_exception: index already exists"
        )
        with patch.object(
            recommendations,
            "req",
            side_effect=[existing, {}],
        ) as request:
            recommendations.ensure_index(
                "https://example.test",
                "elastic",
                "secret",
            )
        self.assertEqual(request.call_count, 2)
        method, url, _, _, body = request.call_args.args
        self.assertEqual(method, "PUT")
        self.assertEqual(
            url,
            "https://example.test/aws-cockpit-recommendations/_mapping",
        )
        self.assertEqual(
            body,
            {"properties": {"@timestamp": {"type": "date"}}},
        )

    def test_missing_metric_index_returns_no_recommendations(self):
        error = RuntimeError(
            "POST https://example.test/_query -> 400: "
            "Unknown index [metrics-aws.s3_daily_storage-default]"
        )
        stderr = io.StringIO()
        with patch.object(recommendations, "req", side_effect=error):
            with contextlib.redirect_stderr(stderr):
                rows = recommendations.esql(
                    "https://example.test",
                    "elastic",
                    "secret",
                    "FROM metrics-aws.s3_daily_storage-default",
                )
        self.assertEqual(rows, [])
        self.assertIn("esql warn", stderr.getvalue())
        self.assertIn("Unknown index", stderr.getvalue())

    def test_successful_query_maps_columns_to_rows(self):
        response = {
            "columns": [{"name": "instance"}, {"name": "avg_cpu"}],
            "values": [["i-123", 4.2]],
        }
        with patch.object(recommendations, "req", return_value=response):
            rows = recommendations.esql(
                "https://example.test",
                "elastic",
                "secret",
                "FROM metrics-aws.ec2_metrics-default",
            )
        self.assertEqual(rows, [{"instance": "i-123", "avg_cpu": 4.2}])

    def test_authentication_errors_remain_fatal(self):
        error = RuntimeError("POST https://example.test/_query -> 401: unauthorized")
        with patch.object(recommendations, "req", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "unauthorized"):
                recommendations.esql(
                    "https://example.test",
                    "elastic",
                    "bad-secret",
                    "FROM metrics-aws.ec2_metrics-default",
                )


class ManifestAssetFallbackTests(unittest.TestCase):
    @patch("seed_aws_insight_indices.subprocess.run")
    def test_builds_s3_inventory_without_daily_metrics(self, run):
        run.return_value.returncode = 0
        run.return_value.stdout = json.dumps(
            {
                "Buckets": [
                    {
                        "Name": "customer-logs",
                        "BucketRegion": "eu-west-1",
                    }
                ]
            }
        )
        docs = aws_s3_asset_docs("2026-09-27T19:05:00.000Z")
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0][1]["resource"]["type"], "s3_bucket")
        self.assertEqual(docs[0][1]["metric_name"], "inventory_only")

    def test_builds_inventory_docs_when_metric_streams_are_absent(self):
        manifest = {
            "discovered_at": "2026-09-27T19:00:00+00:00",
            "resources": [
                {
                    "type": "aws.s3.bucket",
                    "name": "customer-logs",
                    "arn": "arn:aws:s3:::customer-logs",
                    "region": "eu-west-1",
                    "account_id": "123456789012",
                    "configuration": {},
                },
                {
                    "type": "aws.lambda.function",
                    "name": "ignored",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(manifest))
            docs = manifest_asset_docs(
                str(path), "2026-09-27T19:05:00.000Z"
            )
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0][1]["resource"]["type"], "s3_bucket")
        self.assertEqual(docs[0][1]["metric_name"], "inventory_only")


if __name__ == "__main__":
    unittest.main()
