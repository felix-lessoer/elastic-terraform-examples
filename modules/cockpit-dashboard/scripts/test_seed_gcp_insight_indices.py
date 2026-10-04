from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seed_gcp_insight_indices import (
    build_resource_coverage_docs,
    manifest_documents,
)


class GcpManifestIngestionTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {
            "discovered_at": "2026-10-04T12:00:00Z",
            "resources": [
                {
                    "type": "google_compute_instance",
                    "id": "instance-1",
                    "name": "api-1",
                    "project_id": "example-project",
                    "region": "us-central1",
                    "labels": {"owner": "platform"},
                    "dependencies": [
                        {
                            "target": "example-project:global:gcs_bucket:uploads",
                            "type": "reads_from",
                            "evidence": "configured_endpoint",
                            "confidence": 0.8,
                        }
                    ],
                },
                {
                    "type": "google_storage_bucket",
                    "name": "uploads",
                    "project_id": "example-project",
                    "region": "global",
                },
            ],
        }

    def test_manifest_builds_resource_candidates_and_dependencies(self):
        resources, candidates, dependencies = manifest_documents(
            self.manifest, "2026-10-04T12:01:00Z"
        )
        self.assertEqual(len(resources), 2)
        self.assertEqual(len(candidates), 2)
        self.assertEqual(len(dependencies), 1)
        self.assertEqual(resources[0][1]["resource"]["type"], "gce_instance")
        self.assertEqual(dependencies[0][1]["relationship"], "reads_from")

    def test_cloud_asset_manifest_fields_are_normalized(self):
        manifest = {
            "generated_at": "2026-10-04T12:00:00Z",
            "resources": [
                {
                    "project_id": "example-project",
                    "kind": "asset",
                    "resource_id": (
                        "//compute.googleapis.com/projects/example-project/"
                        "zones/us-central1-a/instances/api-1"
                    ),
                    "asset_type": "compute.googleapis.com/Instance",
                    "display_name": "api-1",
                    "location": "us-central1-a",
                    "ownership_hints": {"owner": "platform"},
                    "relationships": ["projects/example-project/global/networks/default"],
                }
            ],
        }
        resources, candidates, dependencies = manifest_documents(
            manifest, "2026-10-04T12:01:00Z"
        )
        self.assertEqual(resources[0][1]["resource"]["type"], "gce_instance")
        self.assertEqual(resources[0][1]["resource"]["name"], "api-1")
        self.assertEqual(resources[0][1]["cloud"]["region"], "us-central1-a")
        self.assertEqual(resources[0][1]["owner"], "platform")
        self.assertEqual(candidates[0][1]["service"], "compute")
        self.assertEqual(len(dependencies), 1)

    @patch("seed_gcp_insight_indices.time.time", return_value=1_759_579_200)
    def test_coverage_is_per_resource_and_missing_signals_are_unknown(self, _time):
        resources, _, _ = manifest_documents(
            self.manifest, "2025-08-25T12:00:00Z"
        )
        compute = resources[0][1]
        assets = [
            (
                "compute",
                {
                    "resource": compute["resource"],
                    "cloud": compute["cloud"],
                    "metric_name": "cpu_avg_24h",
                    "last_seen": 1_759_579_200_000,
                },
            )
        ]
        coverage = build_resource_coverage_docs(
            resources, assets, "2025-08-25T12:00:00Z"
        )
        self.assertEqual(len(coverage), 2)
        compute_coverage = coverage[0][1]
        bucket_coverage = coverage[1][1]
        self.assertTrue(compute_coverage["discovered"])
        self.assertEqual(compute_coverage["signals"]["metrics"]["status"], "fresh")
        self.assertEqual(compute_coverage["signals"]["traces"]["status"], "unknown")
        self.assertEqual(bucket_coverage["status"], "unknown")
        self.assertEqual(
            bucket_coverage["signals"]["metrics"]["status"], "unknown"
        )


if __name__ == "__main__":
    unittest.main()
