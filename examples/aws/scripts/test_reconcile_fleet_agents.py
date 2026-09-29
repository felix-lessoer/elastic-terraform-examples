from datetime import datetime, timezone
import unittest

from reconcile_fleet_agents import stale_agents


def agent(
    identifier: str,
    instance_id: str,
    status: str,
    last_checkin: str,
    *,
    policy_id: str = "aws-policy",
    private_ip: str = "",
) -> dict:
    return {
        "id": identifier,
        "policy_id": policy_id,
        "status": status,
        "last_checkin": last_checkin,
        "local_metadata": {
            "cloud": {"instance": {"id": instance_id}},
            "host": {"ip": [f"{private_ip}/20"] if private_ip else []},
        },
    }


class FleetAgentReconciliationTests(unittest.TestCase):
    def test_removes_only_old_offline_replacements(self):
        agents = [
            agent(
                "current",
                "i-current",
                "online",
                "2026-09-29T07:00:00Z",
            ),
            agent(
                "stale",
                "i-replaced",
                "offline",
                "2026-09-29T04:00:00Z",
            ),
            agent(
                "recent",
                "i-starting",
                "offline",
                "2026-09-29T06:45:00Z",
            ),
        ]
        stale = stale_agents(
            agents,
            policy_id="aws-policy",
            current_instance_id="i-current",
            now=datetime(2026, 9, 29, 7, 0, tzinfo=timezone.utc),
        )
        self.assertEqual([item["id"] for item in stale], ["stale"])

    def test_defers_cleanup_until_current_instance_is_online(self):
        agents = [
            agent(
                "stale",
                "i-replaced",
                "offline",
                "2026-09-29T04:00:00Z",
            )
        ]
        self.assertEqual(
            stale_agents(
                agents,
                policy_id="aws-policy",
                current_instance_id="i-current",
                now=datetime(2026, 9, 29, 7, 0, tzinfo=timezone.utc),
            ),
            [],
        )

    def test_matches_versioned_policy_and_private_ip(self):
        agents = [
            agent(
                "current",
                "",
                "online",
                "2026-09-29T07:00:00Z",
                policy_id="aws-policy#9.6",
                private_ip="172.31.9.155",
            ),
            agent(
                "stale",
                "",
                "offline",
                "2026-09-29T04:00:00Z",
                policy_id="aws-policy#9.5",
                private_ip="172.31.1.10",
            ),
        ]
        stale = stale_agents(
            agents,
            policy_id="aws-policy",
            current_instance_id="i-current",
            current_private_ip="172.31.9.155",
            now=datetime(2026, 9, 29, 7, 0, tzinfo=timezone.utc),
        )
        self.assertEqual([item["id"] for item in stale], ["stale"])


if __name__ == "__main__":
    unittest.main()
