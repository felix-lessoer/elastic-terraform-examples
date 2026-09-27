import contextlib
import io
import unittest
from unittest.mock import patch

import generate_aws_recommendations as recommendations


class EsqlTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
