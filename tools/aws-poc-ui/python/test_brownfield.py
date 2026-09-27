import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from analyze_brownfield import analyze, validate_manifest
from aws_brownfield_discovery import AwsCli, owner_candidates, stable_id, tags_to_dict


class DiscoveryHelpersTest(unittest.TestCase):
    def test_normalizes_tags_and_owner_candidates(self):
        tags = tags_to_dict(
            [
                {"Key": "Name", "Value": "checkout"},
                {"Key": "team", "Value": "payments"},
            ]
        )
        self.assertEqual(tags, {"Name": "checkout", "team": "payments"})
        candidates = owner_candidates(tags)
        self.assertEqual(candidates[0]["value"], "payments")
        self.assertEqual(candidates[0]["source"], "tag.team")

    def test_stable_ids_are_deterministic(self):
        self.assertEqual(stable_id("a", "b"), stable_id("a", "b"))
        self.assertNotEqual(stable_id("a", "b"), stable_id("b", "a"))

    def test_rejects_non_read_only_aws_operations(self):
        client = object.__new__(AwsCli)
        client.executable = "aws"
        client.budget = type("Budget", (), {"consume": lambda self: True})()
        client.errors = []
        client.error_lock = __import__("threading").Lock()
        with self.assertRaises(ValueError):
            client.call("lambda", "update-function-configuration")

    def test_aws_cli_call_works_with_v1_and_disables_paging_via_environment(self):
        client = object.__new__(AwsCli)
        client.executable = "aws"
        client.budget = type("Budget", (), {"consume": lambda self: True})()
        client.errors = []
        client.error_lock = __import__("threading").Lock()
        completed = type(
            "Completed",
            (),
            {
                "returncode": 0,
                "stdout": '{"Account":"123456789012"}',
                "stderr": "",
            },
        )()
        with patch(
            "aws_brownfield_discovery.subprocess.run",
            return_value=completed,
        ) as run:
            result = client.call(
                "sts",
                "get-caller-identity",
                region="eu-west-1",
            )
        command = run.call_args.args[0]
        self.assertNotIn("--no-cli-pager", command)
        self.assertEqual(run.call_args.kwargs["env"]["AWS_PAGER"], "")
        self.assertEqual(result["Account"], "123456789012")


class AnalysisTest(unittest.TestCase):
    def manifest(self):
        return {
            "schema_version": "1.0",
            "discovered_at": "2026-09-27T16:00:00+00:00",
            "limitations": [],
            "resources": [
                {
                    "arn": "arn:aws:lambda:eu-west-1:123456789012:function:checkout",
                    "resource_uid": "lambda",
                    "type": "aws.lambda.function",
                    "name": "checkout",
                    "account_id": "123456789012",
                    "region": "eu-west-1",
                    "state": "active",
                    "tags": {"service": "checkout", "owner": "payments"},
                    "ownership": {
                        "candidates": [
                            {
                                "value": "payments",
                                "source": "tag.owner",
                                "confidence": 0.98,
                            }
                        ]
                    },
                    "configuration": {"tracing_mode": "PassThrough"},
                    "telemetry": {
                        "metrics": "aws_native",
                        "logs": "not_observed",
                        "traces": "not_configured",
                    },
                    "evidence": [{"source": "lambda:ListFunctions"}],
                },
                {
                    "arn": "arn:aws:cloudwatch:eu-west-1:123456789012:alarm:errors",
                    "resource_uid": "alarm",
                    "type": "aws.cloudwatch.alarm",
                    "name": "errors",
                    "account_id": "123456789012",
                    "region": "eu-west-1",
                    "state": "alarm",
                    "tags": {},
                    "ownership": {"candidates": []},
                    "configuration": {"state_reason": "Threshold crossed"},
                    "telemetry": {"events": "observed"},
                    "evidence": [{"source": "cloudwatch:DescribeAlarms"}],
                },
            ],
            "edges": [],
        }

    def test_generates_services_coverage_findings_and_non_executing_proposals(self):
        result = analyze(self.manifest(), "2026-09-27T16:05:00+00:00")
        self.assertEqual(result["summary"]["resources"], 2)
        self.assertEqual(result["summary"]["service_candidates"], 1)
        self.assertGreaterEqual(result["summary"]["findings"], 2)
        self.assertGreaterEqual(result["summary"]["proposals"], 2)
        self.assertTrue(all(item["execution"] == "none" for item in result["proposals"]))
        titles = [item["title"] for item in result["findings"]]
        self.assertTrue(any("CloudWatch alarm is active" in title for title in titles))

    def test_is_deterministic_for_fixed_analysis_time(self):
        first = analyze(self.manifest(), "2026-09-27T16:05:00+00:00")
        second = analyze(self.manifest(), "2026-09-27T16:05:00+00:00")
        self.assertEqual(
            json.dumps(first, sort_keys=True),
            json.dumps(second, sort_keys=True),
        )

    def test_rejects_duplicate_resource_arns(self):
        manifest = self.manifest()
        manifest["resources"].append(dict(manifest["resources"][0]))
        with self.assertRaises(ValueError):
            validate_manifest(manifest)


if __name__ == "__main__":
    unittest.main()
