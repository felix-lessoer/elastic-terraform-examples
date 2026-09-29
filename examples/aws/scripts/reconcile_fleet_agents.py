#!/usr/bin/env python3
"""Remove stale Fleet enrollments after the Terraform collector is online."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


def nested_value(value: dict, *path: str):
    current = value
    for part in path:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def instance_id(agent: dict) -> str:
    metadata = agent.get("local_metadata") or {}
    return str(nested_value(metadata, "cloud", "instance", "id") or "")


def parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def stale_agents(
    agents: list[dict],
    *,
    policy_id: str,
    current_instance_id: str,
    now: datetime | None = None,
) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    matching = [agent for agent in agents if agent.get("policy_id") == policy_id]
    current = next(
        (
            agent
            for agent in matching
            if instance_id(agent) == current_instance_id
            and agent.get("status") in {"online", "updating", "enrolling"}
        ),
        None,
    )
    if not current:
        return []
    cutoff = now - timedelta(hours=1)
    stale = []
    for agent in matching:
        if agent.get("id") == current.get("id"):
            continue
        checked = parse_time(agent.get("last_checkin") or "")
        if agent.get("status") in {"offline", "inactive", "error"} and (
            checked is None or checked < cutoff
        ):
            stale.append(agent)
    return stale


class FleetClient:
    def __init__(self) -> None:
        self.url = os.environ["KIBANA_URL"].rstrip("/")
        credentials = (
            f"{os.environ['KIBANA_USERNAME']}:"
            f"{os.environ['KIBANA_PASSWORD']}"
        )
        self.auth = base64.b64encode(credentials.encode()).decode()

    def request(
        self, method: str, path: str, body: dict | None = None
    ) -> dict:
        request = urllib.request.Request(
            f"{self.url}{path}",
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={
                "Authorization": f"Basic {self.auth}",
                "Content-Type": "application/json",
                "kbn-xsrf": "true",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = response.read()
                return json.loads(payload) if payload else {}
        except urllib.error.HTTPError as error:
            detail = error.read().decode()[:1000]
            raise RuntimeError(
                f"{method} {path} failed ({error.code}): {detail}"
            ) from error

    def agents(self, policy_id: str) -> list[dict]:
        items: list[dict] = []
        page = 1
        while True:
            query = urllib.parse.urlencode(
                {
                    "page": page,
                    "perPage": 100,
                    "kuery": f'policy_id:"{policy_id}"',
                }
            )
            response = self.request("GET", f"/api/fleet/agents?{query}")
            batch = response.get("items", [])
            items.extend(batch)
            total = response.get("total")
            if not batch or (
                isinstance(total, int) and len(items) >= total
            ):
                return items
            if len(batch) < 100:
                return items
            page += 1

    def unenroll(self, agent_id: str) -> None:
        self.request(
            "POST",
            f"/api/fleet/agents/{agent_id}/unenroll",
            {"revoke": True},
        )


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] != "reconcile":
        raise SystemExit("usage: reconcile_fleet_agents.py reconcile")
    policy_id = os.environ["AGENT_POLICY_ID"]
    expected_instance = os.environ["AWS_INSTANCE_ID"]
    client = FleetClient()
    wait_seconds = int(os.environ.get("FLEET_WAIT_SECONDS", "300"))
    deadline = time.monotonic() + wait_seconds
    agents = client.agents(policy_id)
    while not any(
        instance_id(agent) == expected_instance
        and agent.get("status") in {"online", "updating", "enrolling"}
        for agent in agents
    ) and time.monotonic() < deadline:
        time.sleep(min(15, max(0, deadline - time.monotonic())))
        agents = client.agents(policy_id)
    stale = stale_agents(
        agents,
        policy_id=policy_id,
        current_instance_id=expected_instance,
    )
    current_is_ready = any(
        instance_id(agent) == expected_instance
        and agent.get("status") in {"online", "updating", "enrolling"}
        for agent in agents
    )
    if not current_is_ready:
        print(
            "Fleet cleanup deferred until the current Terraform collector "
            "is enrolled",
            flush=True,
        )
        return 0
    for agent in stale:
        client.unenroll(agent["id"])
    print(f"Removed {len(stale)} stale Fleet agent enrollment(s)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
