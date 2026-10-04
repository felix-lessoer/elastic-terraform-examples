import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from gcp_brownfield_discovery import (
    DiscoveryConfig,
    DiscoveryError,
    DiscoveryRunner,
    OPERATIONS,
    validate_manifest,
    write_manifest,
)


PROJECT = "example-project-123"


class FixtureTransport:
    def __init__(self, fixtures):
        self.fixtures = {key: list(values) for key, values in fixtures.items()}
        self.calls = []

    def execute(self, operation, project, page_token, timeout):
        self.calls.append((operation, project, page_token, timeout))
        value = self.fixtures[(operation, page_token)].pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def config(operation, **overrides):
    values = {
        "projects": (PROJECT,),
        "operations": (operation,),
        "max_api_calls": 10,
        "max_resources": 20,
        "max_concurrency": 2,
        "per_call_timeout": 1.5,
        "max_attempts": 3,
        "initial_backoff": 0,
    }
    values.update(overrides)
    return DiscoveryConfig(**values)


class BrownfieldDiscoveryTests(unittest.TestCase):
    def test_success_is_paginated_sanitized_validated_and_hashed(self):
        operation = "asset.searchAllResources"
        transport = FixtureTransport(
            {
                (operation, None): [
                    {
                        "results": [
                            {
                                "name": "//compute.googleapis.com/projects/p/zones/z/instances/i",
                                "assetType": "compute.googleapis.com/Instance",
                                "location": "us-central1-a",
                                "state": "RUNNING",
                                "labels": {
                                    "owner": "platform",
                                    "api_key": "must-not-appear",
                                },
                                "additionalAttributes": {
                                    "createTime": "2026-01-01T00:00:00Z",
                                    "password": "must-not-appear",
                                },
                                "serviceAccount": "collector@example-project-123.iam.gserviceaccount.com",
                            }
                        ],
                        "nextPageToken": "next",
                    }
                ],
                (operation, "next"): [{"results": []}],
            }
        )
        events = []
        manifest = DiscoveryRunner(transport, progress=events.append).run(
            config(operation)
        )

        validate_manifest(manifest)
        self.assertTrue(manifest["summary"]["complete"])
        self.assertEqual(manifest["summary"]["api_calls"], 2)
        self.assertEqual(manifest["resources"][0]["labels"]["api_key"], "[redacted]")
        self.assertNotIn("must-not-appear", json.dumps(manifest))
        self.assertTrue(any(event["event"] == "page_complete" for event in events))

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "manifest.json"
            result = write_manifest(manifest, output)
            self.assertEqual(
                result["manifest_sha256"],
                hashlib.sha256(output.read_bytes()).hexdigest(),
            )

    def test_denied_retains_result_without_raising(self):
        operation = "logging.sinks.list"
        transport = FixtureTransport(
            {(operation, None): [DiscoveryError("denied", 403)]}
        )
        manifest = DiscoveryRunner(transport).run(config(operation))
        self.assertFalse(manifest["summary"]["complete"])
        self.assertEqual(manifest["operation_results"][0]["status"], "denied")
        self.assertEqual(manifest["resources"], [])

    def test_throttled_call_retries_with_backoff(self):
        operation = "pubsub.topics.list"
        transport = FixtureTransport(
            {
                (operation, None): [
                    DiscoveryError("throttled", 429),
                    {"topics": [{"name": f"projects/{PROJECT}/topics/logs"}]},
                ]
            }
        )
        delays = []
        manifest = DiscoveryRunner(transport, sleep=delays.append).run(
            config(operation, initial_backoff=0.5)
        )
        self.assertEqual(delays, [0.5])
        self.assertEqual(manifest["summary"]["api_calls"], 2)
        self.assertEqual(manifest["summary"]["resources"], 1)

    def test_empty_response_is_complete(self):
        operation = "monitoring.alertPolicies.list"
        transport = FixtureTransport(
            {(operation, None): [{"alertPolicies": []}]}
        )
        manifest = DiscoveryRunner(transport).run(config(operation))
        self.assertTrue(manifest["summary"]["complete"])
        self.assertEqual(manifest["summary"]["resources"], 0)

    def test_timeout_after_first_page_keeps_partial_results(self):
        operation = "pubsub.subscriptions.list"
        transport = FixtureTransport(
            {
                (operation, None): [
                    {
                        "subscriptions": [
                            {
                                "name": f"projects/{PROJECT}/subscriptions/logs",
                                "topic": f"projects/{PROJECT}/topics/logs",
                            }
                        ],
                        "nextPageToken": "next",
                    }
                ],
                (operation, "next"): [
                    DiscoveryError("timeout"),
                    DiscoveryError("timeout"),
                ],
            }
        )
        manifest = DiscoveryRunner(transport).run(
            config(operation, max_attempts=2)
        )
        result = manifest["operation_results"][0]
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["error"], "timeout")
        self.assertEqual(result["resources"], 1)
        self.assertEqual(transport.calls[-1][-1], 1.5)

    def test_global_resource_budget_truncates_output(self):
        operation = "serviceusage.services.list"
        transport = FixtureTransport(
            {
                (operation, None): [
                    {
                        "services": [
                            {"name": f"projects/{PROJECT}/services/a", "state": "ENABLED"},
                            {"name": f"projects/{PROJECT}/services/b", "state": "ENABLED"},
                        ]
                    }
                ]
            }
        )
        manifest = DiscoveryRunner(transport).run(
            config(operation, max_resources=1)
        )
        self.assertEqual(len(manifest["resources"]), 1)
        self.assertEqual(manifest["operation_results"][0]["status"], "partial")
        self.assertEqual(
            manifest["operation_results"][0]["error"],
            "resource_budget_exhausted",
        )

    def test_rejects_non_allowlisted_operations_and_invalid_projects(self):
        with self.assertRaises(ValueError):
            DiscoveryConfig(
                projects=(PROJECT,), operations=("secrets.versions.access",)
            ).validate()
        with self.assertRaises(ValueError):
            DiscoveryConfig(
                projects=("projects/escaped",), operations=(next(iter(OPERATIONS)),)
            ).validate()


if __name__ == "__main__":
    unittest.main()
