import contextlib
import io
import unittest
from unittest.mock import patch

import generate_gcp_recommendations as recommendations


class GcpRecommendationTests(unittest.TestCase):
    def test_resource_key_is_stable_and_scoped(self):
        self.assertEqual(
            recommendations.resource_key(
                "project-a", "europe-west3", "gce_instance", "123"
            ),
            "project-a:europe-west3:gce_instance:123",
        )

    def test_missing_activity_metrics_never_create_unused_finding(self):
        rows = [
            {
                "observations": 10,
                "avg_cpu": 0.1,
                "network_in": None,
                "network_out": None,
                "instance": "vm-one",
                "instance_id": "123",
                "project": "project-a",
                "region": "europe-west3",
            }
        ]
        self.assertEqual(
            recommendations.build_recommendations(rows, [], "2026-10-04T00:00:00Z"),
            [],
        )

    def test_observed_inactivity_creates_deterministic_complete_finding(self):
        row = {
            "observations": 50,
            "avg_cpu": 0.2,
            "network_in": 10,
            "network_out": 20,
            "instance": "vm-one",
            "instance_id": "123",
            "project": "project-a",
            "region": "europe-west3",
        }
        first = recommendations.build_recommendations(
            [row], [], "2026-10-04T00:00:00Z"
        )
        second = recommendations.build_recommendations(
            [row], [], "2026-10-05T00:00:00Z"
        )
        self.assertEqual(first[0][0], second[0][0])
        document = first[0][1]
        self.assertEqual(document["category"], "unused_resource")
        self.assertEqual(document["activity_status"], "potentially_unused")
        self.assertEqual(document["lookback_days"], 14)
        self.assertEqual(
            document["resource"]["key"],
            "project-a:europe-west3:gce_instance:123",
        )
        for field in (
            "evidence_refs",
            "confidence",
            "contradictory_evidence",
            "missing_telemetry",
            "expected_value",
            "safe_next_action",
        ):
            self.assertIn(field, document)

    def test_storage_requires_observations_size_and_request_activity(self):
        base = {
            "bucket": "empty",
            "project": "project-a",
            "region": "us",
            "size": 0,
            "requests": 0,
        }
        self.assertEqual(
            recommendations.build_recommendations(
                [], [{**base, "observations": 0}], "now"
            ),
            [],
        )
        findings = recommendations.build_recommendations(
            [], [{**base, "observations": 3}], "now"
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0][1]["resource"]["type"], "gcs_bucket")

    def test_missing_indices_are_nonfatal_but_authentication_is_fatal(self):
        with patch.object(
            recommendations,
            "req",
            side_effect=RuntimeError("Unknown index [metrics-gcp.compute-default]"),
        ):
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(
                    recommendations.esql("https://es", "elastic", "secret", "query"),
                    [],
                )
        with patch.object(
            recommendations, "req", side_effect=RuntimeError("401 unauthorized")
        ):
            with self.assertRaisesRegex(RuntimeError, "unauthorized"):
                recommendations.esql("https://es", "elastic", "bad", "query")

    def test_queries_are_bounded(self):
        with open(recommendations.__file__, encoding="utf-8") as source:
            text = source.read()
        self.assertGreaterEqual(text.count("| LIMIT 200"), 2)
        self.assertNotIn("%Y%m%d", text)


if __name__ == "__main__":
    unittest.main()
