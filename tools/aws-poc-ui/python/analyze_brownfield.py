#!/usr/bin/env python3
"""Deterministic local analysis of the AWS brownfield discovery manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ANALYZER_VERSION = "1.0.0"
OWNER_TAGS = ("owner", "team", "service", "service.name", "application", "app")
SERVICE_TYPES = {
    "aws.autoscaling.group",
    "aws.ecs.service",
    "aws.eks.cluster",
    "aws.lambda.function",
    "aws.apigateway.rest_api",
    "aws.apigatewayv2.api",
}
SHARED_TYPES = {
    "aws.ec2.vpc",
    "aws.ec2.subnet",
    "aws.ec2.security_group",
    "aws.rds.cluster",
    "aws.rds.instance",
    "aws.sns.topic",
    "aws.events.rule",
    "aws.elbv2.load_balancer",
    "aws.elbv2.target_group",
}
EXPECTED_SIGNALS = {
    "aws.ec2.instance": {"metrics": "required", "logs": "recommended", "traces": "recommended"},
    "aws.autoscaling.group": {"metrics": "required"},
    "aws.ecs.service": {"metrics": "required", "logs": "recommended", "traces": "recommended"},
    "aws.eks.cluster": {"metrics": "required", "logs": "recommended", "traces": "recommended"},
    "aws.lambda.function": {"metrics": "required", "logs": "required", "traces": "recommended"},
    "aws.elbv2.load_balancer": {"metrics": "required", "logs": "recommended"},
    "aws.elbv2.target_group": {"metrics": "required"},
    "aws.rds.instance": {"metrics": "required", "logs": "recommended"},
    "aws.rds.cluster": {"metrics": "required", "logs": "recommended"},
    "aws.apigateway.rest_api": {"metrics": "required", "logs": "recommended", "traces": "recommended"},
    "aws.apigatewayv2.api": {"metrics": "required", "logs": "recommended", "traces": "recommended"},
    "aws.sns.topic": {"metrics": "required"},
    "aws.events.rule": {"metrics": "recommended"},
}


def stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def owner(resource: dict[str, Any]) -> tuple[str | None, str]:
    candidates = resource.get("ownership", {}).get("candidates", [])
    if candidates:
        first = sorted(candidates, key=lambda item: -float(item.get("confidence", 0)))[0]
        return str(first.get("value")), str(first.get("source", "unknown"))
    tags = {str(key).lower(): str(value) for key, value in resource.get("tags", {}).items()}
    for key in OWNER_TAGS:
        if tags.get(key):
            return tags[key], f"tag.{key}"
    return None, "unknown"


def service_name(resource: dict[str, Any]) -> tuple[str, str, float]:
    tags = {str(key).lower(): str(value) for key, value in resource.get("tags", {}).items()}
    for key in ("service.name", "service", "application", "app"):
        if tags.get(key):
            return tags[key], f"tag.{key}", 0.98 if key.startswith("service") else 0.9
    return str(resource.get("name") or resource["arn"]), "resource-boundary", 0.85


def telemetry_status(raw: Any) -> str:
    value = str(raw or "unknown").lower()
    if value in ("observed",):
        return "observed"
    if value in ("configured", "aws_native"):
        return "configured"
    if value in ("not_configured", "not_observed"):
        return "not_observed"
    if value == "not_applicable":
        return "not_applicable"
    return "unknown"


def finding(
    category: str,
    severity: str,
    title: str,
    explanation: str,
    resource_arns: list[str],
    evidence: list[dict[str, Any]],
    confidence: str = "high",
) -> dict[str, Any]:
    impact = {"critical": 1.0, "high": 0.8, "medium": 0.55, "low": 0.3, "info": 0.1}[severity]
    confidence_weight = {
        "confirmed": 1.0,
        "high": 0.85,
        "medium": 0.65,
        "low": 0.4,
        "unknown": 0.2,
    }[confidence]
    identifier = stable_id(category, title, *sorted(resource_arns))
    return {
        "id": identifier,
        "category": category,
        "severity": severity,
        "priority": round(100 * impact * confidence_weight),
        "confidence": confidence,
        "resource_arns": sorted(resource_arns),
        "title": title,
        "explanation": explanation,
        "evidence": evidence,
    }


def proposal(
    resource: dict[str, Any],
    signal: str,
    change: str,
    prerequisites: list[str],
    costs: list[str],
    validation: list[str],
    rollback: list[str],
    priority: int,
) -> dict[str, Any]:
    arn = resource["arn"]
    return {
        "id": stable_id(arn, signal, change),
        "resource_arn": arn,
        "resource_name": resource["name"],
        "resource_type": resource["type"],
        "signal": signal,
        "priority": priority,
        "confidence": "high",
        "execution": "none",
        "change_summary": change,
        "prerequisites": prerequisites,
        "cost_dimensions": costs,
        "validation": validation,
        "rollback": rollback,
        "evidence": [
            {
                "source": "brownfield-manifest",
                "assertion": f"{signal} status is {telemetry_status(resource.get('telemetry', {}).get(signal))}",
            }
        ],
    }


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema_version") != "1.0":
        raise ValueError("Unsupported manifest schema version")
    resources = manifest.get("resources")
    edges = manifest.get("edges")
    if not isinstance(resources, list) or not isinstance(edges, list):
        raise ValueError("Manifest must contain resource and edge arrays")
    arns = [resource.get("arn") for resource in resources]
    if any(not isinstance(arn, str) or not arn for arn in arns):
        raise ValueError("Every resource requires an ARN")
    if len(arns) != len(set(arns)):
        raise ValueError("Manifest contains duplicate resource ARNs")


def analyze(manifest: dict[str, Any], analyzed_at: str) -> dict[str, Any]:
    validate_manifest(manifest)
    resources = manifest["resources"]
    edges = manifest["edges"]
    by_arn = {resource["arn"]: resource for resource in resources}

    services: list[dict[str, Any]] = []
    service_by_resource: dict[str, str] = {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    grouping_meta: dict[str, tuple[str, float]] = {}
    for resource in resources:
        if resource["type"] not in SERVICE_TYPES:
            continue
        name, source, confidence = service_name(resource)
        grouping_key = f"{resource['account_id']}|{resource['region']}|{name.lower()}"
        grouped[grouping_key].append(resource)
        grouping_meta[grouping_key] = (source, confidence)
    for grouping_key, members in sorted(grouped.items()):
        name, _, _ = service_name(members[0])
        source, confidence = grouping_meta[grouping_key]
        service_id = stable_id("service", grouping_key)
        member_arns = sorted(member["arn"] for member in members)
        service_owner, owner_source = owner(members[0])
        services.append(
            {
                "id": service_id,
                "name": name,
                "account_id": members[0]["account_id"],
                "region": members[0]["region"],
                "resource_arns": member_arns,
                "owner": service_owner,
                "owner_source": owner_source,
                "confidence": "confirmed" if confidence >= 0.95 else "high",
                "grouping_evidence": source,
            }
        )
        for arn in member_arns:
            service_by_resource[arn] = service_id

    dependencies = []
    for edge in edges:
        confidence = float(edge.get("confidence", 0))
        dependencies.append(
            {
                **edge,
                "from_service_id": service_by_resource.get(edge.get("from_arn")),
                "to_service_id": service_by_resource.get(edge.get("to_arn")),
                "application_dependency": (
                    edge.get("relation")
                    in ("invokes", "routes_to", "publishes_to", "subscribes_to")
                    and not (
                        by_arn.get(edge.get("to_arn"), {}).get("type") in SHARED_TYPES
                        and confidence < 0.9
                    )
                ),
            }
        )

    coverage: list[dict[str, Any]] = []
    required_observed = 0
    required_known = 0
    for resource in resources:
        expectations = EXPECTED_SIGNALS.get(resource["type"], {})
        for signal, importance in expectations.items():
            status = telemetry_status(resource.get("telemetry", {}).get(signal))
            if importance == "required" and status not in ("unknown", "not_applicable"):
                required_known += 1
                if status == "observed":
                    required_observed += 1
            coverage.append(
                {
                    "resource_arn": resource["arn"],
                    "resource_name": resource["name"],
                    "resource_type": resource["type"],
                    "signal": signal,
                    "importance": importance,
                    "status": status,
                    "service_id": service_by_resource.get(resource["arn"]),
                    "evidence": resource.get("evidence", []),
                }
            )

    findings: list[dict[str, Any]] = []
    proposals: list[dict[str, Any]] = []
    for resource in resources:
        arn = resource["arn"]
        resource_owner, _ = owner(resource)
        if resource["type"] in SERVICE_TYPES and not resource_owner:
            findings.append(
                finding(
                    "ownership",
                    "low",
                    f"No owner found for {resource['name']}",
                    "No supported ownership tag was discovered. This blocks reliable routing.",
                    [arn],
                    resource.get("evidence", []),
                    "confirmed",
                )
            )

        if resource["type"] == "aws.cloudwatch.alarm" and resource["state"] == "alarm":
            findings.append(
                finding(
                    "health",
                    "high",
                    f"CloudWatch alarm is active: {resource['name']}",
                    resource.get("configuration", {}).get("state_reason")
                    or "AWS reports the alarm in ALARM state.",
                    [arn],
                    resource.get("evidence", []),
                    "confirmed",
                )
            )
        if resource["type"] == "aws.elbv2.target_group":
            unhealthy = int(resource.get("configuration", {}).get("unhealthy_target_count", 0))
            if unhealthy:
                findings.append(
                    finding(
                        "health",
                        "high",
                        f"{unhealthy} unhealthy target(s) in {resource['name']}",
                        "ELB target health reported non-healthy registered targets.",
                        [arn],
                        resource.get("evidence", []),
                        "confirmed",
                    )
                )
        if resource["type"] == "aws.ecs.service":
            config = resource.get("configuration", {})
            desired = int(config.get("desired_count") or 0)
            running = int(config.get("running_count") or 0)
            if running < desired:
                findings.append(
                    finding(
                        "health",
                        "high",
                        f"ECS service {resource['name']} is below desired capacity",
                        f"Running tasks: {running}; desired tasks: {desired}.",
                        [arn],
                        resource.get("evidence", []),
                        "confirmed",
                    )
                )
        if resource["type"] == "aws.autoscaling.group":
            config = resource.get("configuration", {})
            desired = int(config.get("desired_capacity") or 0)
            actual = int(config.get("instance_count") or 0)
            if actual < desired:
                findings.append(
                    finding(
                        "health",
                        "high",
                        f"Auto Scaling group {resource['name']} is below desired capacity",
                        f"Instances: {actual}; desired capacity: {desired}.",
                        [arn],
                        resource.get("evidence", []),
                        "confirmed",
                    )
                )

        for row in [item for item in coverage if item["resource_arn"] == arn]:
            if row["importance"] == "required" and row["status"] == "not_observed":
                findings.append(
                    finding(
                        "coverage",
                        "medium",
                        f"{row['signal'].title()} not observed for {resource['name']}",
                        "A required signal is known to be absent from the discovered configuration.",
                        [arn],
                        row["evidence"],
                        "high",
                    )
                )

        telemetry = resource.get("telemetry", {})
        if resource["type"] == "aws.lambda.function":
            if telemetry_status(telemetry.get("logs")) == "not_observed":
                proposals.append(
                    proposal(
                        resource,
                        "logs",
                        "Confirm function logging and collect its existing CloudWatch log group.",
                        ["Function owner approval", "CloudWatch log group and retention decision"],
                        ["CloudWatch Logs ingestion", "Elastic log ingestion and retention"],
                        ["A new invocation produces a searchable log event", "No function errors increase"],
                        ["Remove only the PoC log collection attachment"],
                        85,
                    )
                )
            if telemetry_status(telemetry.get("traces")) == "not_observed":
                proposals.append(
                    proposal(
                        resource,
                        "traces",
                        "Canary an Elastic or OpenTelemetry Lambda layer on a named alias/version.",
                        ["Function owner approval", "Supported runtime", "Version/alias rollback target"],
                        ["Additional invocation duration", "Trace ingestion", "Potential cold-start overhead"],
                        ["Trace reaches Elastic", "Error and duration remain within agreed bounds"],
                        ["Restore previous layers, environment, tracing mode, and alias"],
                        75,
                    )
                )
        elif resource["type"] == "aws.ecs.service" and telemetry_status(telemetry.get("traces")) in (
            "unknown",
            "not_observed",
        ):
            config = resource.get("configuration", {})
            running = int(config.get("running_count") or 0)
            desired = int(config.get("desired_count") or 0)
            proposals.append(
                proposal(
                    resource,
                    "traces",
                    "Inspect the existing task definition for OTel/APM before proposing a canary revision.",
                    ["Service owner approval", "Runtime identification", "Existing agent conflict check"],
                    ["Task CPU/memory", "Trace ingestion", "Deployment replacement"],
                    ["Canary task is healthy", "Trace continuity is demonstrated"],
                    ["Redeploy the previous task definition revision"],
                    80 if running > 0 and desired > 0 else 60,
                )
            )
        elif resource["type"] == "aws.eks.cluster":
            proposals.append(
                proposal(
                    resource,
                    "metrics",
                    "Request scoped Kubernetes API access and assess existing collectors before deployment.",
                    [
                        "Cluster owner approval",
                        "Temporary EKS cluster-admin access for adapter setup",
                        "RBAC review",
                        "Fargate/node-group assessment",
                    ],
                    ["Collector compute", "Metrics/log ingestion"],
                    ["Cluster and node health become visible", "No workload restart for infrastructure collection"],
                    ["Remove the approved collector release and RBAC objects"],
                    55,
                )
            )
        elif resource["type"] == "aws.rds.instance":
            config = resource.get("configuration", {})
            if not config.get("performance_insights_enabled"):
                proposals.append(
                    proposal(
                        resource,
                        "database",
                        "Evaluate Performance Insights and selected engine log exports for this existing database.",
                        ["Database owner approval", "Engine support and retention review"],
                        ["Performance Insights", "CloudWatch Logs", "Elastic ingestion"],
                        ["Query-level evidence improves without database health regression"],
                        ["Restore previous monitoring and log-export settings"],
                        50,
                    )
                )

    findings.sort(key=lambda item: (-item["priority"], item["id"]))
    proposals.sort(key=lambda item: (-item["priority"], item["id"]))
    services.sort(key=lambda item: (item["name"], item["id"]))
    dependencies.sort(key=lambda item: (item["relation"], item["from_arn"], item["to_arn"]))
    coverage.sort(key=lambda item: (item["resource_type"], item["resource_arn"], item["signal"]))
    severity_counts = Counter(item["severity"] for item in findings)

    return {
        "schema_version": "1.0",
        "analyzer_version": ANALYZER_VERSION,
        "catalog_versions": {
            "resource_expectations": "1.0.0",
            "ownership": "1.0.0",
            "proposals": "1.0.0",
        },
        "manifest_digest": canonical_digest(manifest),
        "analyzed_at": analyzed_at,
        "summary": {
            "resources": len(resources),
            "service_candidates": len(services),
            "dependencies": len(dependencies),
            "findings": len(findings),
            "proposals": len(proposals),
            "findings_by_severity": dict(sorted(severity_counts.items())),
            "required_coverage": {
                "numerator": required_observed,
                "denominator": required_known,
                "percentage": (
                    round(required_observed / required_known * 100, 1)
                    if required_known
                    else None
                ),
            },
        },
        "services": services,
        "dependencies": dependencies,
        "coverage": coverage,
        "findings": findings,
        "proposals": proposals,
        "limitations": [
            *manifest.get("limitations", []),
            "Configured AWS-native metrics are not proof that recent documents reached Elastic.",
            "A control-plane manifest cannot establish arbitrary runtime request flow.",
            "Instrumentation proposals are descriptive only and have execution set to none.",
            "Unknown telemetry is excluded from the coverage denominator.",
            "No finding interprets missing evidence as healthy.",
        ],
    }


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--analyzed-at", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    manifest = json.loads(args.manifest.read_text())
    analyzed_at = args.analyzed_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    result = analyze(manifest, analyzed_at)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
