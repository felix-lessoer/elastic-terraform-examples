import unittest

from sync_existing_log_integrations import desired_policy_groups


def lambda_source(index: int, region: str = "eu-west-1") -> dict:
    return {
        "kind": "cloudwatch",
        "region": region,
        "log_group_name": f"/aws/lambda/function-{index}",
        "policy_template": "lambda",
        "input_type": "aws-cloudwatch",
        "dataset": "aws.lambda_logs",
    }


class ExistingLogPolicyGroupingTests(unittest.TestCase):
    def test_groups_selected_lambda_functions_into_bounded_policies(self):
        groups = desired_policy_groups(
            [lambda_source(index) for index in range(101)]
        )
        self.assertEqual([len(sources) for _, sources in groups], [50, 50, 1])
        self.assertEqual(len({name for name, _ in groups}), 3)

    def test_separates_regions(self):
        groups = desired_policy_groups(
            [lambda_source(1), lambda_source(2, "us-east-2")]
        )
        self.assertEqual(len(groups), 2)
        self.assertTrue(any("eu-west-1" in name for name, _ in groups))
        self.assertTrue(any("us-east-2" in name for name, _ in groups))


if __name__ == "__main__":
    unittest.main()
