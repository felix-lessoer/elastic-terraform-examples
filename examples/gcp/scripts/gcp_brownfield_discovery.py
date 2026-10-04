#!/usr/bin/env python3
"""Bounded, read-only GCP brownfield discovery.

The runner deliberately exposes only a fixed set of GET operations. It writes
the validated manifest locally and prints only its digest and summary.
Production authentication uses Application Default Credentials; tests inject a
transport and therefore never require GCP credentials.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import threading
import time
from typing import Any, Callable, Protocol
import urllib.error
import urllib.parse
import urllib.request


SCHEMA_VERSION = "1.0"
PROJECT_RE = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
SECRET_KEY_RE = re.compile(
    r"(secret|password|passwd|private.?key|credential|access.?token|api.?key)",
    re.IGNORECASE,
)
SERVICE_ACCOUNT_RE = re.compile(
    r"(?:serviceAccount:)?[a-z0-9-]+@[a-z0-9.-]+\.iam\.gserviceaccount\.com"
)
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class Operation:
    path: str
    items_key: str | None
    kind: str
    params: tuple[tuple[str, str], ...] = ()


# This is both the operation allow-list and the complete production API surface.
# Every operation is read-only and constrained to an approved project scope.
OPERATIONS: dict[str, Operation] = {
    "asset.searchAllResources": Operation(
        "https://cloudasset.googleapis.com/v1/projects/{project}:searchAllResources",
        "results",
        "asset",
        (("pageSize", "500"),),
    ),
    "logging.sinks.list": Operation(
        "https://logging.googleapis.com/v2/projects/{project}/sinks",
        "sinks",
        "logging_sink",
        (("pageSize", "1000"),),
    ),
    "logging.buckets.list": Operation(
        "https://logging.googleapis.com/v2/projects/{project}/locations/-/buckets",
        "buckets",
        "logging_bucket",
        (("pageSize", "1000"),),
    ),
    "pubsub.topics.list": Operation(
        "https://pubsub.googleapis.com/v1/projects/{project}/topics",
        "topics",
        "pubsub_topic",
        (("pageSize", "1000"),),
    ),
    "pubsub.subscriptions.list": Operation(
        "https://pubsub.googleapis.com/v1/projects/{project}/subscriptions",
        "subscriptions",
        "pubsub_subscription",
        (("pageSize", "1000"),),
    ),
    "monitoring.alertPolicies.list": Operation(
        "https://monitoring.googleapis.com/v3/projects/{project}/alertPolicies",
        "alertPolicies",
        "alert_policy",
        (("pageSize", "1000"),),
    ),
    "monitoring.metricsScopes.get": Operation(
        "https://monitoring.googleapis.com/v1/locations/global/metricsScopes/{project}",
        None,
        "metrics_scope",
    ),
    "serviceusage.services.list": Operation(
        "https://serviceusage.googleapis.com/v1/projects/{project}/services",
        "services",
        "enabled_service",
        (("filter", "state:ENABLED"), ("pageSize", "200")),
    ),
}


class DiscoveryError(Exception):
    """A transport failure with a safe, classified status."""

    def __init__(self, category: str, status: int | None = None):
        super().__init__(category)
        self.category = category
        self.status = status


class DiscoveryTransport(Protocol):
    def execute(
        self,
        operation: str,
        project: str,
        page_token: str | None,
        timeout: float,
    ) -> dict[str, Any]:
        """Execute one allow-listed API call."""


class GoogleRestTransport:
    """ADC-authenticated implementation of the fixed read-only REST surface."""

    def __init__(self) -> None:
        try:
            import google.auth  # type: ignore[import-not-found]
            from google.auth.transport.requests import Request  # type: ignore[import-not-found]
        except ImportError as error:
            raise RuntimeError(
                "google-auth is required for live discovery; install google-auth "
                "or inject a test transport"
            ) from error
        self._credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform.read-only"]
        )
        self._request = Request()
        self._lock = threading.Lock()

    def _token(self) -> str:
        with self._lock:
            if not self._credentials.valid:
                self._credentials.refresh(self._request)
            return str(self._credentials.token)

    def execute(
        self,
        operation: str,
        project: str,
        page_token: str | None,
        timeout: float,
    ) -> dict[str, Any]:
        spec = OPERATIONS[operation]
        query = dict(spec.params)
        if page_token:
            query["pageToken"] = page_token
        url = spec.path.format(project=urllib.parse.quote(project, safe=""))
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"
        request = urllib.request.Request(
            url,
            method="GET",
            headers={"Authorization": f"Bearer {self._token()}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read()
        except urllib.error.HTTPError as error:
            category = "denied" if error.code in {401, 403} else "api_error"
            if error.code == 429:
                category = "throttled"
            raise DiscoveryError(category, error.code) from None
        except (TimeoutError, urllib.error.URLError):
            raise DiscoveryError("timeout") from None
        try:
            decoded = json.loads(payload) if payload else {}
        except json.JSONDecodeError:
            raise DiscoveryError("invalid_response") from None
        if not isinstance(decoded, dict):
            raise DiscoveryError("invalid_response")
        return decoded


@dataclass(frozen=True)
class DiscoveryConfig:
    projects: tuple[str, ...]
    operations: tuple[str, ...] = tuple(OPERATIONS)
    max_api_calls: int = 100
    max_resources: int = 5000
    max_concurrency: int = 4
    per_call_timeout: float = 15.0
    max_attempts: int = 3
    initial_backoff: float = 0.25

    def validate(self) -> None:
        if not self.projects or any(not PROJECT_RE.fullmatch(p) for p in self.projects):
            raise ValueError("projects must contain valid GCP project IDs")
        if len(set(self.projects)) != len(self.projects):
            raise ValueError("projects must not contain duplicates")
        unknown = set(self.operations) - set(OPERATIONS)
        if unknown:
            raise ValueError(f"operations are not allow-listed: {sorted(unknown)}")
        if len(set(self.operations)) != len(self.operations):
            raise ValueError("operations must not contain duplicates")
        for name, value in (
            ("max_api_calls", self.max_api_calls),
            ("max_resources", self.max_resources),
            ("max_concurrency", self.max_concurrency),
            ("max_attempts", self.max_attempts),
        ):
            if value < 1:
                raise ValueError(f"{name} must be positive")
        if self.per_call_timeout <= 0 or self.initial_backoff < 0:
            raise ValueError("timeouts must be positive and backoff non-negative")


class Budget:
    def __init__(self, calls: int, resources: int):
        self.calls_remaining = calls
        self.resources_remaining = resources
        self.lock = threading.Lock()

    def reserve_call(self) -> bool:
        with self.lock:
            if self.calls_remaining == 0:
                return False
            self.calls_remaining -= 1
            return True

    def take_resources(self, count: int) -> int:
        with self.lock:
            accepted = min(count, self.resources_remaining)
            self.resources_remaining -= accepted
            return accepted


def _safe_labels(labels: Any) -> dict[str, str]:
    if not isinstance(labels, dict):
        return {}
    return {
        str(key): "[redacted]" if SECRET_KEY_RE.search(str(key)) else str(value)[:256]
        for key, value in sorted(labels.items())
    }


def _service_accounts(value: Any) -> list[str]:
    found: set[str] = set()

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if not SECRET_KEY_RE.search(str(key)):
                    visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)
        elif isinstance(item, str):
            found.update(SERVICE_ACCOUNT_RE.findall(item))

    visit(value)
    return sorted(found)


def _select(source: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    selected: dict[str, Any] = {}
    for field in fields:
        value = source.get(field)
        if value is not None and not SECRET_KEY_RE.search(field):
            selected[field] = value
    return selected


def normalize_item(kind: str, item: dict[str, Any], project: str) -> dict[str, Any]:
    """Reduce API responses to a secret-free, stable discovery record."""
    common = {"project_id": project, "kind": kind}
    if kind == "asset":
        labels = _safe_labels(item.get("labels"))
        additional = item.get("additionalAttributes", {})
        deployment = (
            _select(
                additional,
                (
                    "createTime",
                    "updateTime",
                    "status",
                    "state",
                    "version",
                    "environment",
                ),
            )
            if isinstance(additional, dict)
            else {}
        )
        ownership = {
            key: value
            for key, value in labels.items()
            if key.lower() in {"owner", "team", "managed-by", "goog-gke-node"}
        }
        relationships = item.get("relationships", {})
        relationship_ids: list[str] = []
        if isinstance(relationships, dict):
            for relationship in relationships.values():
                if isinstance(relationship, dict):
                    assets = relationship.get("relatedResources", [])
                    if isinstance(assets, list):
                        relationship_ids.extend(
                            str(asset)
                            for asset in assets
                            if isinstance(asset, str)
                        )
        return {
            **common,
            "resource_id": str(item.get("name", "")),
            "asset_type": str(item.get("assetType", "")),
            "display_name": str(item.get("displayName", "")),
            "location": str(item.get("location", "")),
            "state": str(item.get("state", additional.get("state", "")))
            if isinstance(additional, dict)
            else str(item.get("state", "")),
            "labels": labels,
            "ownership_hints": ownership,
            "deployment_metadata": deployment,
            "service_account_references": _service_accounts(item),
            "relationships": sorted(set(relationship_ids)),
        }

    fields_by_kind = {
        "logging_sink": (
            "name",
            "destination",
            "filter",
            "disabled",
            "writerIdentity",
            "includeChildren",
        ),
        "logging_bucket": (
            "name",
            "retentionDays",
            "locked",
            "lifecycleState",
            "analyticsEnabled",
        ),
        "pubsub_topic": ("name", "messageStoragePolicy"),
        "pubsub_subscription": (
            "name",
            "topic",
            "ackDeadlineSeconds",
            "retainAckedMessages",
            "expirationPolicy",
            "deadLetterPolicy",
        ),
        "alert_policy": ("name", "displayName", "enabled", "combiner"),
        "metrics_scope": ("name", "monitoredProjects"),
        "enabled_service": ("name", "state"),
    }
    result = {**common, **_select(item, fields_by_kind[kind])}
    if kind in {"pubsub_topic", "pubsub_subscription"}:
        result["labels"] = _safe_labels(item.get("labels"))
    accounts = _service_accounts(result)
    if accounts:
        result["service_account_references"] = accounts
    return result


def validate_manifest(manifest: dict[str, Any]) -> None:
    """Validate the versioned contract without requiring jsonschema at runtime."""
    required = {
        "schema_version",
        "generated_at",
        "approved_projects",
        "limits",
        "resources",
        "operation_results",
        "summary",
    }
    if set(manifest) != required:
        raise ValueError("manifest has unexpected or missing top-level fields")
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported manifest schema version")
    if not isinstance(manifest["resources"], list):
        raise ValueError("resources must be an array")
    if not isinstance(manifest["operation_results"], list):
        raise ValueError("operation_results must be an array")
    projects = set(manifest["approved_projects"])
    for resource in manifest["resources"]:
        if not isinstance(resource, dict) or resource.get("project_id") not in projects:
            raise ValueError("resource escapes approved project scope")
        if resource.get("kind") not in {spec.kind for spec in OPERATIONS.values()}:
            raise ValueError("resource kind is not allow-listed")
        if any(SECRET_KEY_RE.search(str(key)) for key in resource):
            raise ValueError("secret-like field found in manifest")
    for result in manifest["operation_results"]:
        if result.get("operation") not in OPERATIONS:
            raise ValueError("operation result is not allow-listed")


class DiscoveryRunner:
    def __init__(
        self,
        transport: DiscoveryTransport,
        *,
        sleep: Callable[[float], None] = time.sleep,
        progress: Callable[[dict[str, Any]], None] | None = None,
    ):
        self.transport = transport
        self.sleep = sleep
        self.progress = progress or (lambda event: None)
        self._progress_lock = threading.Lock()

    def _emit(self, **event: Any) -> None:
        with self._progress_lock:
            self.progress(event)

    def run(self, config: DiscoveryConfig) -> dict[str, Any]:
        config.validate()
        budget = Budget(config.max_api_calls, config.max_resources)
        resources: list[dict[str, Any]] = []
        operation_results: list[dict[str, Any]] = []

        def discover(project: str, operation: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
            self._emit(event="operation_started", project_id=project, operation=operation)
            discovered: list[dict[str, Any]] = []
            page_token: str | None = None
            calls = 0
            status = "success"
            error: str | None = None
            truncated = False
            while True:
                response: dict[str, Any] | None = None
                for attempt in range(config.max_attempts):
                    if not budget.reserve_call():
                        status, error, truncated = "partial", "call_budget_exhausted", True
                        break
                    calls += 1
                    try:
                        response = self.transport.execute(
                            operation, project, page_token, config.per_call_timeout
                        )
                        break
                    except DiscoveryError as failure:
                        retryable = (
                            failure.status in RETRYABLE_STATUS
                            or failure.category in {"timeout", "throttled"}
                        )
                        if retryable and attempt + 1 < config.max_attempts:
                            delay = config.initial_backoff * (2**attempt)
                            self._emit(
                                event="retry",
                                project_id=project,
                                operation=operation,
                                attempt=attempt + 1,
                                reason=failure.category,
                                delay_seconds=delay,
                            )
                            self.sleep(delay)
                            continue
                        status = "partial" if discovered else failure.category
                        error = failure.category
                        break
                if response is None:
                    break
                spec = OPERATIONS[operation]
                raw_items = (
                    response.get(spec.items_key, []) if spec.items_key else [response]
                )
                if not isinstance(raw_items, list):
                    status, error = "invalid_response", "invalid_response"
                    break
                normalized = [
                    normalize_item(spec.kind, item, project)
                    for item in raw_items
                    if isinstance(item, dict)
                ]
                accepted = budget.take_resources(len(normalized))
                discovered.extend(normalized[:accepted])
                self._emit(
                    event="page_complete",
                    project_id=project,
                    operation=operation,
                    resources=len(discovered),
                )
                if accepted < len(normalized):
                    status, error, truncated = "partial", "resource_budget_exhausted", True
                    break
                page_token_value = response.get("nextPageToken")
                page_token = str(page_token_value) if page_token_value else None
                if not page_token:
                    break
            result = {
                "project_id": project,
                "operation": operation,
                "status": status,
                "api_calls": calls,
                "resources": len(discovered),
                "truncated": truncated,
            }
            if error:
                result["error"] = error
            self._emit(event="operation_complete", **result)
            return discovered, result

        tasks = [
            (project, operation)
            for project in config.projects
            for operation in config.operations
        ]
        with ThreadPoolExecutor(
            max_workers=min(config.max_concurrency, len(tasks))
        ) as executor:
            futures = {
                executor.submit(discover, project, operation): (project, operation)
                for project, operation in tasks
            }
            for future in as_completed(futures):
                found, result = future.result()
                resources.extend(found)
                operation_results.append(result)

        resources.sort(
            key=lambda value: (
                value["project_id"],
                value["kind"],
                str(value.get("resource_id", value.get("name", ""))),
            )
        )
        operation_results.sort(key=lambda value: (value["project_id"], value["operation"]))
        statuses: dict[str, int] = {}
        for result in operation_results:
            statuses[result["status"]] = statuses.get(result["status"], 0) + 1
        summary = {
            "complete": all(result["status"] == "success" for result in operation_results),
            "projects": len(config.projects),
            "operations": len(operation_results),
            "api_calls": sum(result["api_calls"] for result in operation_results),
            "resources": len(resources),
            "resources_by_kind": {
                kind: sum(resource["kind"] == kind for resource in resources)
                for kind in sorted({resource["kind"] for resource in resources})
            },
            "statuses": statuses,
        }
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "approved_projects": list(config.projects),
            "limits": {
                "max_api_calls": config.max_api_calls,
                "max_resources": config.max_resources,
                "max_concurrency": config.max_concurrency,
                "per_call_timeout_seconds": config.per_call_timeout,
                "max_attempts": config.max_attempts,
            },
            "resources": resources,
            "operation_results": operation_results,
            "summary": summary,
        }
        validate_manifest(manifest)
        return manifest


def write_manifest(manifest: dict[str, Any], output: Path) -> dict[str, Any]:
    encoded = (
        json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_bytes(encoded)
    temporary.replace(output)
    return {"manifest_sha256": digest, "summary": manifest["summary"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", action="append", required=True)
    parser.add_argument("--operation", action="append", choices=sorted(OPERATIONS))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-api-calls", type=int, default=100)
    parser.add_argument("--max-resources", type=int, default=5000)
    parser.add_argument("--max-concurrency", type=int, default=4)
    parser.add_argument("--per-call-timeout", type=float, default=15.0)
    parser.add_argument("--max-attempts", type=int, default=3)
    args = parser.parse_args(argv)
    config = DiscoveryConfig(
        projects=tuple(args.project),
        operations=tuple(args.operation or OPERATIONS),
        max_api_calls=args.max_api_calls,
        max_resources=args.max_resources,
        max_concurrency=args.max_concurrency,
        per_call_timeout=args.per_call_timeout,
        max_attempts=args.max_attempts,
    )
    runner = DiscoveryRunner(
        GoogleRestTransport(),
        progress=lambda event: print(
            json.dumps(event, sort_keys=True), file=sys.stderr, flush=True
        ),
    )
    manifest = runner.run(config)
    print(json.dumps(write_manifest(manifest, args.output), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
