#!/usr/bin/env python3
"""Read-only AWS brownfield discovery for the local PoC deployment creator."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable


OWNER_TAGS = (
    "owner",
    "team",
    "service",
    "service.name",
    "application",
    "app",
    "cost-center",
)
CORE_SERVICE_TYPES = {
    "aws.autoscaling.group",
    "aws.ecs.service",
    "aws.eks.cluster",
    "aws.lambda.function",
    "aws.apigateway.rest_api",
    "aws.apigatewayv2.api",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_id(*parts: str) -> str:
    value = "|".join(parts).encode()
    return hashlib.sha256(value).hexdigest()[:32]


def tags_to_dict(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        return {str(key): str(value) for key, value in sorted(raw.items())}
    if not isinstance(raw, list):
        return {}
    result: dict[str, str] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        key = item.get("Key") or item.get("key")
        value = item.get("Value") if "Value" in item else item.get("value")
        if key is not None and value is not None:
            result[str(key)] = str(value)
    return dict(sorted(result.items()))


def owner_candidates(tags: dict[str, str]) -> list[dict[str, Any]]:
    lowered = {key.lower(): (key, value) for key, value in tags.items()}
    candidates = []
    for position, tag_name in enumerate(OWNER_TAGS):
        match = lowered.get(tag_name)
        if match and match[1].strip():
            candidates.append(
                {
                    "value": match[1].strip(),
                    "source": f"tag.{match[0]}",
                    "confidence": round(max(0.65, 0.98 - position * 0.04), 2),
                }
            )
    return candidates


@dataclass
class Budget:
    maximum: int
    calls: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def consume(self) -> bool:
        with self.lock:
            if self.calls >= self.maximum:
                return False
            self.calls += 1
            return True


class AwsCli:
    """Bounded AWS CLI runner. All callers use explicit read-only operations."""

    def __init__(self, maximum_calls: int) -> None:
        self.executable = shutil.which("aws")
        if not self.executable:
            raise RuntimeError("AWS CLI was not found in PATH")
        self.budget = Budget(maximum_calls)
        self.errors: list[dict[str, Any]] = []
        self.error_lock = threading.Lock()

    def call(
        self,
        service: str,
        operation: str,
        *,
        region: str | None = None,
        args: Iterable[str] = (),
        optional: bool = False,
        timeout: int = 90,
    ) -> dict[str, Any]:
        if not operation.startswith(
            ("list-", "describe-", "get-", "batch-get-", "lookup-", "search-")
        ):
            raise ValueError(f"Non-read-only AWS operation rejected: {operation}")
        if not self.budget.consume():
            self._error(service, operation, region, "ApiBudgetExceeded", "API call budget exhausted")
            return {}
        command = [self.executable, service, operation, *args]
        if region:
            command.extend(["--region", region])
        command.extend(
            [
                "--output",
                "json",
                "--cli-connect-timeout",
                "5",
                "--cli-read-timeout",
                "20",
            ]
        )
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                env={**os.environ, "AWS_PAGER": ""},
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            self._error(service, operation, region, "Timeout", f"Timed out after {timeout}s")
            return {}
        if result.returncode != 0:
            message = result.stderr.strip() or f"AWS CLI exited with {result.returncode}"
            known_optional = any(
                marker in message
                for marker in (
                    "AccessDenied",
                    "UnauthorizedOperation",
                    "UnrecognizedClient",
                    "InvalidAction",
                    "UnknownOperation",
                    "is not supported in this region",
                )
            )
            if not optional or not known_optional:
                self._error(service, operation, region, "AwsCliError", message[-1_000:])
            else:
                self._error(service, operation, region, "Unavailable", message[-1_000:])
            return {}
        if not result.stdout.strip():
            return {}
        try:
            value = json.loads(result.stdout)
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError as error:
            self._error(service, operation, region, "InvalidJson", str(error))
            return {}

    def _error(
        self,
        service: str,
        operation: str,
        region: str | None,
        code: str,
        message: str,
    ) -> None:
        with self.error_lock:
            self.errors.append(
                {
                    "scope": f"{region or 'global'}/{service}/{operation}",
                    "code": code,
                    "message": message,
                }
            )


class RegionDiscovery:
    def __init__(
        self,
        aws: AwsCli,
        account_id: str,
        partition: str,
        observed_at: str,
        max_per_type: int,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        self.aws = aws
        self.account_id = account_id
        self.partition = partition
        self.observed_at = observed_at
        self.max_per_type = max_per_type
        self.progress = progress or (lambda _message: None)
        self.resources: dict[str, dict[str, Any]] = {}
        self.edges: dict[str, dict[str, Any]] = {}
        self.log_groups: set[str] = set()

    def resource(
        self,
        resource_type: str,
        region: str,
        stable_identifier: str,
        name: str,
        *,
        arn: str | None = None,
        state: str = "unknown",
        tags: Any = None,
        configuration: dict[str, Any] | None = None,
        telemetry: dict[str, Any] | None = None,
        evidence: str,
    ) -> str:
        resource_arn = arn or (
            f"arn:{self.partition}:elastic-poc-discovery:{region}:"
            f"{self.account_id}:{resource_type}/{stable_identifier}"
        )
        normalized_tags = tags_to_dict(tags)
        uid = stable_id(self.account_id, region, resource_type, resource_arn)
        config = configuration or {}
        document = {
            "schema_version": "1.0",
            "resource_uid": uid,
            "arn": resource_arn,
            "type": resource_type,
            "name": name,
            "account_id": self.account_id,
            "region": region,
            "state": str(state or "unknown").lower(),
            "tags": normalized_tags,
            "configuration": config,
            "configuration_hash": hashlib.sha256(
                json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "ownership": {"candidates": owner_candidates(normalized_tags)},
            "telemetry": telemetry or {},
            "evidence": [{"source": evidence, "observed_at": self.observed_at}],
        }
        self.resources[uid] = document
        return resource_arn

    def edge(
        self,
        from_arn: str | None,
        relation: str,
        to_arn: str | None,
        evidence: str,
        *,
        confidence: float = 0.95,
        deterministic: bool = True,
    ) -> None:
        if not from_arn or not to_arn or from_arn == to_arn:
            return
        uid = stable_id(from_arn, relation, to_arn)
        self.edges[uid] = {
            "schema_version": "1.0",
            "edge_uid": uid,
            "from_arn": from_arn,
            "to_arn": to_arn,
            "relation": relation,
            "confidence": confidence,
            "classification": (
                "confirmed" if confidence >= 0.9 else "probable" if confidence >= 0.7 else "candidate"
            ),
            "deterministic": deterministic,
            "evidence": [{"source": evidence, "observed_at": self.observed_at}],
        }

    def discover(self, region: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        scans = [
            ("CloudWatch logs", self._logs),
            ("EC2 instances", self._ec2),
            ("Auto Scaling groups", self._autoscaling),
            ("ECS services", self._ecs),
            ("EKS clusters", self._eks),
            ("Lambda functions", self._lambda),
            ("load balancers", self._elbv2),
            ("RDS databases", self._rds),
            ("API Gateway APIs", self._api_gateway),
            ("messaging services", self._messaging),
            ("CloudWatch alarms", self._alarms),
            ("X-Ray dependencies", self._xray),
        ]
        self.progress(f"[{region}] Discovery started")
        for label, scan in scans:
            self.progress(f"[{region}] Scanning {label}…")
            scan(region)
        self.progress(
            f"[{region}] Complete: {len(self.resources)} resources, "
            f"{len(self.edges)} dependencies"
        )
        return list(self.resources.values()), list(self.edges.values())

    def _logs(self, region: str) -> None:
        data = self.aws.call(
            "logs",
            "describe-log-groups",
            region=region,
            args=("--limit", str(min(50, self.max_per_type))),
            optional=True,
        )
        for group in data.get("logGroups", [])[: self.max_per_type]:
            name = group.get("logGroupName")
            if not name:
                continue
            self.log_groups.add(name)
            self.resource(
                "aws.logs.log_group",
                region,
                name,
                name,
                arn=str(group.get("arn", "")).removesuffix(":*") or None,
                state="active",
                configuration={
                    "retention_days": group.get("retentionInDays"),
                    "stored_bytes": group.get("storedBytes"),
                    "kms_key_id": group.get("kmsKeyId"),
                },
                telemetry={"logs": "configured"},
                evidence="logs:DescribeLogGroups",
            )

    def _ec2(self, region: str) -> None:
        data = self.aws.call("ec2", "describe-instances", region=region, optional=True)
        count = 0
        for reservation in data.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                if count >= self.max_per_type:
                    return
                instance_id = instance.get("InstanceId")
                if not instance_id:
                    continue
                count += 1
                arn = f"arn:{self.partition}:ec2:{region}:{self.account_id}:instance/{instance_id}"
                instance_arn = self.resource(
                    "aws.ec2.instance",
                    region,
                    instance_id,
                    next(
                        (
                            tag["Value"]
                            for tag in instance.get("Tags", [])
                            if tag.get("Key") == "Name"
                        ),
                        instance_id,
                    ),
                    arn=arn,
                    state=instance.get("State", {}).get("Name", "unknown"),
                    tags=instance.get("Tags"),
                    configuration={
                        "instance_type": instance.get("InstanceType"),
                        "image_id": instance.get("ImageId"),
                        "availability_zone": instance.get("Placement", {}).get("AvailabilityZone"),
                        "vpc_id": instance.get("VpcId"),
                        "subnet_id": instance.get("SubnetId"),
                        "security_group_ids": [
                            group.get("GroupId") for group in instance.get("SecurityGroups", [])
                        ],
                        "iam_instance_profile_arn": instance.get("IamInstanceProfile", {}).get("Arn"),
                        "launch_time": instance.get("LaunchTime"),
                    },
                    telemetry={"metrics": "aws_native", "logs": "unknown", "traces": "unknown"},
                    evidence="ec2:DescribeInstances",
                )
                for relation, target_type, target_id in (
                    ("attached_to", "vpc", instance.get("VpcId")),
                    ("attached_to", "subnet", instance.get("SubnetId")),
                ):
                    if target_id:
                        target = (
                            f"arn:{self.partition}:ec2:{region}:{self.account_id}:"
                            f"{target_type}/{target_id}"
                        )
                        self.edge(instance_arn, relation, target, "ec2:DescribeInstances")

    def _autoscaling(self, region: str) -> None:
        data = self.aws.call(
            "autoscaling", "describe-auto-scaling-groups", region=region, optional=True
        )
        for group in data.get("AutoScalingGroups", [])[: self.max_per_type]:
            name = group.get("AutoScalingGroupName")
            arn = group.get("AutoScalingGroupARN")
            if not name or not arn:
                continue
            group_arn = self.resource(
                "aws.autoscaling.group",
                region,
                name,
                name,
                arn=arn,
                state="active",
                tags=group.get("Tags"),
                configuration={
                    "desired_capacity": group.get("DesiredCapacity"),
                    "min_size": group.get("MinSize"),
                    "max_size": group.get("MaxSize"),
                    "instance_count": len(group.get("Instances", [])),
                    "target_group_arns": group.get("TargetGroupARNs", []),
                    "launch_template": group.get("LaunchTemplate"),
                },
                telemetry={"metrics": "aws_native", "logs": "not_applicable"},
                evidence="autoscaling:DescribeAutoScalingGroups",
            )
            for instance in group.get("Instances", []):
                instance_id = instance.get("InstanceId")
                if instance_id:
                    self.edge(
                        f"arn:{self.partition}:ec2:{region}:{self.account_id}:instance/{instance_id}",
                        "member_of",
                        group_arn,
                        "autoscaling:DescribeAutoScalingGroups",
                    )
            for target in group.get("TargetGroupARNs", []):
                self.edge(group_arn, "routes_to", target, "autoscaling:DescribeAutoScalingGroups")

    def _ecs(self, region: str) -> None:
        clusters = self.aws.call("ecs", "list-clusters", region=region, optional=True).get(
            "clusterArns", []
        )[: self.max_per_type]
        for cluster_arn in clusters:
            cluster_name = cluster_arn.rsplit("/", 1)[-1]
            self.resource(
                "aws.ecs.cluster",
                region,
                cluster_arn,
                cluster_name,
                arn=cluster_arn,
                state="active",
                telemetry={"metrics": "aws_native"},
                evidence="ecs:ListClusters",
            )
            service_arns = self.aws.call(
                "ecs",
                "list-services",
                region=region,
                args=("--cluster", cluster_arn),
                optional=True,
            ).get("serviceArns", [])[: self.max_per_type]
            for start in range(0, len(service_arns), 10):
                batch = service_arns[start : start + 10]
                described = self.aws.call(
                    "ecs",
                    "describe-services",
                    region=region,
                    args=("--cluster", cluster_arn, "--services", *batch),
                    optional=True,
                )
                for service in described.get("services", []):
                    service_arn = service.get("serviceArn")
                    if not service_arn:
                        continue
                    name = service.get("serviceName", service_arn.rsplit("/", 1)[-1])
                    resource_arn = self.resource(
                        "aws.ecs.service",
                        region,
                        service_arn,
                        name,
                        arn=service_arn,
                        state=service.get("status", "unknown"),
                        tags=service.get("tags"),
                        configuration={
                            "cluster_arn": cluster_arn,
                            "task_definition": service.get("taskDefinition"),
                            "desired_count": service.get("desiredCount"),
                            "running_count": service.get("runningCount"),
                            "pending_count": service.get("pendingCount"),
                            "launch_type": service.get("launchType"),
                            "platform_version": service.get("platformVersion"),
                            "target_group_arns": [
                                item.get("targetGroupArn")
                                for item in service.get("loadBalancers", [])
                                if item.get("targetGroupArn")
                            ],
                        },
                        telemetry={"metrics": "aws_native", "logs": "unknown", "traces": "unknown"},
                        evidence="ecs:DescribeServices",
                    )
                    self.edge(resource_arn, "member_of", cluster_arn, "ecs:DescribeServices")
                    self.edge(
                        resource_arn,
                        "defined_by",
                        service.get("taskDefinition"),
                        "ecs:DescribeServices",
                    )
                    for item in service.get("loadBalancers", []):
                        self.edge(
                            resource_arn,
                            "routes_to",
                            item.get("targetGroupArn"),
                            "ecs:DescribeServices",
                        )

    def _eks(self, region: str) -> None:
        names = self.aws.call("eks", "list-clusters", region=region, optional=True).get(
            "clusters", []
        )[: self.max_per_type]
        for name in names:
            cluster = self.aws.call(
                "eks",
                "describe-cluster",
                region=region,
                args=("--name", name),
                optional=True,
            ).get("cluster", {})
            arn = cluster.get("arn")
            if not arn:
                continue
            self.resource(
                "aws.eks.cluster",
                region,
                name,
                name,
                arn=arn,
                state=cluster.get("status", "unknown"),
                tags=cluster.get("tags"),
                configuration={
                    "version": cluster.get("version"),
                    "platform_version": cluster.get("platformVersion"),
                    "endpoint_public_access": cluster.get("resourcesVpcConfig", {}).get(
                        "endpointPublicAccess"
                    ),
                    "endpoint_private_access": cluster.get("resourcesVpcConfig", {}).get(
                        "endpointPrivateAccess"
                    ),
                    "logging": cluster.get("logging"),
                },
                telemetry={"metrics": "unknown", "logs": "configured" if cluster.get("logging") else "unknown", "traces": "unknown"},
                evidence="eks:DescribeCluster",
            )

    def _lambda(self, region: str) -> None:
        data = self.aws.call("lambda", "list-functions", region=region, optional=True)
        for function in data.get("Functions", [])[: self.max_per_type]:
            name = function.get("FunctionName")
            arn = function.get("FunctionArn")
            if not name or not arn:
                continue
            log_group = f"/aws/lambda/{name}"
            function_arn = self.resource(
                "aws.lambda.function",
                region,
                name,
                name,
                arn=arn,
                state="active",
                configuration={
                    "runtime": function.get("Runtime"),
                    "architectures": function.get("Architectures", []),
                    "memory_size": function.get("MemorySize"),
                    "timeout": function.get("Timeout"),
                    "last_modified": function.get("LastModified"),
                    "layers": [layer.get("Arn") for layer in function.get("Layers", [])],
                    "tracing_mode": function.get("TracingConfig", {}).get("Mode", "unknown"),
                    "vpc_id": function.get("VpcConfig", {}).get("VpcId"),
                    "environment_keys": sorted(
                        function.get("Environment", {}).get("Variables", {}).keys()
                    ),
                },
                telemetry={
                    "metrics": "aws_native",
                    "logs": "configured" if log_group in self.log_groups else "not_observed",
                    "log_group": log_group,
                    "traces": (
                        "configured"
                        if function.get("TracingConfig", {}).get("Mode") == "Active"
                        else "not_configured"
                    ),
                },
                evidence="lambda:ListFunctions",
            )
            if log_group in self.log_groups:
                log_arn = next(
                    (
                        resource["arn"]
                        for resource in self.resources.values()
                        if resource["type"] == "aws.logs.log_group"
                        and resource["name"] == log_group
                    ),
                    None,
                )
                self.edge(function_arn, "logs_to", log_arn, "logs:DescribeLogGroups")
        mappings = self.aws.call(
            "lambda", "list-event-source-mappings", region=region, optional=True
        )
        for mapping in mappings.get("EventSourceMappings", [])[: self.max_per_type]:
            self.edge(
                mapping.get("EventSourceArn"),
                "invokes",
                mapping.get("FunctionArn"),
                "lambda:ListEventSourceMappings",
            )

    def _elbv2(self, region: str) -> None:
        load_balancers = self.aws.call(
            "elbv2", "describe-load-balancers", region=region, optional=True
        ).get("LoadBalancers", [])[: self.max_per_type]
        for load_balancer in load_balancers:
            arn = load_balancer.get("LoadBalancerArn")
            if not arn:
                continue
            self.resource(
                "aws.elbv2.load_balancer",
                region,
                arn,
                load_balancer.get("LoadBalancerName", arn.rsplit("/", 1)[-1]),
                arn=arn,
                state=load_balancer.get("State", {}).get("Code", "unknown"),
                configuration={
                    "type": load_balancer.get("Type"),
                    "scheme": load_balancer.get("Scheme"),
                    "dns_name": load_balancer.get("DNSName"),
                    "vpc_id": load_balancer.get("VpcId"),
                    "security_groups": load_balancer.get("SecurityGroups", []),
                },
                telemetry={"metrics": "aws_native", "logs": "unknown"},
                evidence="elbv2:DescribeLoadBalancers",
            )
        target_groups = self.aws.call(
            "elbv2", "describe-target-groups", region=region, optional=True
        ).get("TargetGroups", [])[: self.max_per_type]
        for target_group in target_groups:
            arn = target_group.get("TargetGroupArn")
            if not arn:
                continue
            target_arn = self.resource(
                "aws.elbv2.target_group",
                region,
                arn,
                target_group.get("TargetGroupName", arn.rsplit("/", 1)[-1]),
                arn=arn,
                state="active",
                configuration={
                    "protocol": target_group.get("Protocol"),
                    "port": target_group.get("Port"),
                    "target_type": target_group.get("TargetType"),
                    "vpc_id": target_group.get("VpcId"),
                },
                telemetry={"metrics": "aws_native"},
                evidence="elbv2:DescribeTargetGroups",
            )
            for load_balancer_arn in target_group.get("LoadBalancerArns", []):
                self.edge(
                    load_balancer_arn,
                    "routes_to",
                    target_arn,
                    "elbv2:DescribeTargetGroups",
                )
            health = self.aws.call(
                "elbv2",
                "describe-target-health",
                region=region,
                args=("--target-group-arn", arn),
                optional=True,
            )
            unhealthy = []
            for description in health.get("TargetHealthDescriptions", []):
                target = description.get("Target", {})
                state = description.get("TargetHealth", {}).get("State", "unknown")
                target_id = target.get("Id")
                unhealthy.append(state) if state != "healthy" else None
                if target_id and target_group.get("TargetType") == "instance":
                    destination = (
                        f"arn:{self.partition}:ec2:{region}:{self.account_id}:instance/{target_id}"
                    )
                    self.edge(target_arn, "routes_to", destination, "elbv2:DescribeTargetHealth")
            resource = next(
                item for item in self.resources.values() if item["arn"] == target_arn
            )
            resource["configuration"]["unhealthy_target_count"] = len(unhealthy)

    def _rds(self, region: str) -> None:
        clusters = self.aws.call(
            "rds", "describe-db-clusters", region=region, optional=True
        ).get("DBClusters", [])[: self.max_per_type]
        for cluster in clusters:
            arn = cluster.get("DBClusterArn")
            if not arn:
                continue
            self.resource(
                "aws.rds.cluster",
                region,
                arn,
                cluster.get("DBClusterIdentifier", arn.rsplit(":", 1)[-1]),
                arn=arn,
                state=cluster.get("Status", "unknown"),
                configuration={
                    "engine": cluster.get("Engine"),
                    "engine_version": cluster.get("EngineVersion"),
                    "multi_az": cluster.get("MultiAZ"),
                    "log_exports": cluster.get("EnabledCloudwatchLogsExports", []),
                    "members": cluster.get("DBClusterMembers", []),
                },
                telemetry={"metrics": "aws_native", "logs": "configured" if cluster.get("EnabledCloudwatchLogsExports") else "not_configured", "traces": "not_applicable"},
                evidence="rds:DescribeDBClusters",
            )
        instances = self.aws.call(
            "rds", "describe-db-instances", region=region, optional=True
        ).get("DBInstances", [])[: self.max_per_type]
        for instance in instances:
            arn = instance.get("DBInstanceArn")
            if not arn:
                continue
            instance_arn = self.resource(
                "aws.rds.instance",
                region,
                arn,
                instance.get("DBInstanceIdentifier", arn.rsplit(":", 1)[-1]),
                arn=arn,
                state=instance.get("DBInstanceStatus", "unknown"),
                configuration={
                    "engine": instance.get("Engine"),
                    "instance_class": instance.get("DBInstanceClass"),
                    "multi_az": instance.get("MultiAZ"),
                    "cluster_identifier": instance.get("DBClusterIdentifier"),
                    "performance_insights_enabled": instance.get(
                        "PerformanceInsightsEnabled", False
                    ),
                    "monitoring_interval": instance.get("MonitoringInterval", 0),
                    "log_exports": instance.get("EnabledCloudwatchLogsExports", []),
                },
                telemetry={"metrics": "aws_native", "logs": "configured" if instance.get("EnabledCloudwatchLogsExports") else "not_configured", "traces": "not_applicable"},
                evidence="rds:DescribeDBInstances",
            )
            cluster_identifier = instance.get("DBClusterIdentifier")
            if cluster_identifier:
                cluster_arn = next(
                    (
                        resource["arn"]
                        for resource in self.resources.values()
                        if resource["type"] == "aws.rds.cluster"
                        and resource["name"] == cluster_identifier
                    ),
                    None,
                )
                self.edge(instance_arn, "member_of", cluster_arn, "rds:DescribeDBInstances")

    def _api_gateway(self, region: str) -> None:
        rest_apis = self.aws.call(
            "apigateway",
            "get-rest-apis",
            region=region,
            args=("--limit", str(min(500, self.max_per_type))),
            optional=True,
        ).get("items", [])[: self.max_per_type]
        for api in rest_apis:
            api_id = api.get("id")
            if not api_id:
                continue
            arn = f"arn:{self.partition}:apigateway:{region}::/restapis/{api_id}"
            self.resource(
                "aws.apigateway.rest_api",
                region,
                api_id,
                api.get("name", api_id),
                arn=arn,
                state="active",
                tags=api.get("tags"),
                configuration={
                    "endpoint_types": api.get("endpointConfiguration", {}).get("types", []),
                    "created_date": api.get("createdDate"),
                },
                telemetry={"metrics": "aws_native", "logs": "unknown", "traces": "unknown"},
                evidence="apigateway:GetRestApis",
            )
        v2_apis = self.aws.call(
            "apigatewayv2", "get-apis", region=region, optional=True
        ).get("Items", [])[: self.max_per_type]
        for api in v2_apis:
            api_id = api.get("ApiId")
            if not api_id:
                continue
            arn = f"arn:{self.partition}:apigateway:{region}::/apis/{api_id}"
            self.resource(
                "aws.apigatewayv2.api",
                region,
                api_id,
                api.get("Name", api_id),
                arn=arn,
                state="active",
                tags=api.get("Tags"),
                configuration={
                    "protocol_type": api.get("ProtocolType"),
                    "api_endpoint": api.get("ApiEndpoint"),
                    "disable_execute_api_endpoint": api.get("DisableExecuteApiEndpoint"),
                },
                telemetry={"metrics": "aws_native", "logs": "unknown", "traces": "unknown"},
                evidence="apigatewayv2:GetApis",
            )

    def _messaging(self, region: str) -> None:
        for topic in self.aws.call(
            "sns", "list-topics", region=region, optional=True
        ).get("Topics", [])[: self.max_per_type]:
            arn = topic.get("TopicArn")
            if arn:
                self.resource(
                    "aws.sns.topic",
                    region,
                    arn,
                    arn.rsplit(":", 1)[-1],
                    arn=arn,
                    state="active",
                    telemetry={"metrics": "aws_native"},
                    evidence="sns:ListTopics",
                )
        for rule in self.aws.call(
            "events", "list-rules", region=region, optional=True
        ).get("Rules", [])[: self.max_per_type]:
            arn = rule.get("Arn")
            name = rule.get("Name")
            if not arn or not name:
                continue
            rule_arn = self.resource(
                "aws.events.rule",
                region,
                arn,
                name,
                arn=arn,
                state=rule.get("State", "unknown"),
                configuration={"event_bus_name": rule.get("EventBusName", "default")},
                telemetry={"metrics": "aws_native"},
                evidence="events:ListRules",
            )
            targets = self.aws.call(
                "events",
                "list-targets-by-rule",
                region=region,
                args=("--rule", name, "--event-bus-name", rule.get("EventBusName", "default")),
                optional=True,
            )
            for target in targets.get("Targets", []):
                self.edge(rule_arn, "invokes", target.get("Arn"), "events:ListTargetsByRule")

    def _alarms(self, region: str) -> None:
        alarms = self.aws.call(
            "cloudwatch", "describe-alarms", region=region, optional=True
        ).get("MetricAlarms", [])[: self.max_per_type]
        for alarm in alarms:
            arn = alarm.get("AlarmArn")
            name = alarm.get("AlarmName")
            if not arn or not name:
                continue
            self.resource(
                "aws.cloudwatch.alarm",
                region,
                arn,
                name,
                arn=arn,
                state=alarm.get("StateValue", "unknown"),
                configuration={
                    "namespace": alarm.get("Namespace"),
                    "metric_name": alarm.get("MetricName"),
                    "dimensions": alarm.get("Dimensions", []),
                    "state_reason": alarm.get("StateReason"),
                    "state_updated_timestamp": alarm.get("StateUpdatedTimestamp"),
                },
                telemetry={"events": "observed"},
                evidence="cloudwatch:DescribeAlarms",
            )

    def _xray(self, region: str) -> None:
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=1)
        data = self.aws.call(
            "xray",
            "get-service-graph",
            region=region,
            args=("--start-time", start.isoformat(), "--end-time", end.isoformat()),
            optional=True,
        )
        reference_map: dict[int, str] = {}
        for service in data.get("Services", [])[: self.max_per_type]:
            reference_id = service.get("ReferenceId")
            name = service.get("Name") or service.get("Names", ["unknown"])[0]
            synthetic_arn = (
                f"arn:{self.partition}:xray:{region}:{self.account_id}:service/{name}"
            )
            service_arn = self.resource(
                "aws.xray.service",
                region,
                str(reference_id),
                name,
                arn=synthetic_arn,
                state="observed",
                configuration={"type": service.get("Type"), "account_id": service.get("AccountId")},
                telemetry={"traces": "observed"},
                evidence="xray:GetServiceGraph",
            )
            if isinstance(reference_id, int):
                reference_map[reference_id] = service_arn
        for service in data.get("Services", [])[: self.max_per_type]:
            source = reference_map.get(service.get("ReferenceId"))
            for edge in service.get("Edges", []):
                target = reference_map.get(edge.get("ReferenceId"))
                self.edge(
                    source,
                    "invokes",
                    target,
                    "xray:GetServiceGraph",
                    confidence=0.98,
                    deterministic=False,
                )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap-region", default="")
    parser.add_argument("--region", action="append", dest="regions")
    parser.add_argument("--max-api-calls", type=int, default=2_000)
    parser.add_argument("--max-resources-per-type", type=int, default=500)
    parser.add_argument("--parallel-regions", type=int, default=4)
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    progress_lock = threading.Lock()

    def progress(message: str) -> None:
        with progress_lock:
            print(message, flush=True)

    if args.max_api_calls < 10 or args.max_resources_per_type < 1:
        raise SystemExit("Discovery limits must be positive")
    aws = AwsCli(args.max_api_calls)
    bootstrap_region = (
        args.bootstrap_region
        or __import__("os").environ.get("AWS_REGION")
        or __import__("os").environ.get("AWS_DEFAULT_REGION")
        or "us-east-1"
    )
    progress(f"Verifying AWS caller identity in {bootstrap_region}…")
    identity = aws.call("sts", "get-caller-identity", region=bootstrap_region)
    account_id = str(identity.get("Account", ""))
    caller_arn = str(identity.get("Arn", ""))
    if not account_id:
        detail = aws.errors[-1]["message"] if aws.errors else "AWS returned no account ID"
        raise SystemExit(f"Unable to resolve AWS caller identity: {detail}")
    partition = caller_arn.split(":", 2)[1] if caller_arn.startswith("arn:") else "aws"
    observed_at = utc_now()

    regions = args.regions
    if not regions:
        region_data = aws.call(
            "ec2",
            "describe-regions",
            region=bootstrap_region,
            args=("--all-regions",),
        )
        regions = sorted(
            region["RegionName"]
            for region in region_data.get("Regions", [])
            if region.get("RegionName")
            and region.get("OptInStatus") != "not-opted-in"
        )
    if not regions:
        regions = [bootstrap_region]
    worker_count = max(1, min(args.parallel_regions, 16))
    progress(
        f"Scanning {len(regions)} enabled AWS regions with "
        f"{worker_count} parallel workers"
    )

    all_resources: dict[str, dict[str, Any]] = {}
    all_edges: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                RegionDiscovery(
                    aws,
                    account_id,
                    partition,
                    observed_at,
                    args.max_resources_per_type,
                    progress,
                ).discover,
                region,
            ): region
            for region in regions
        }
        for future in as_completed(futures):
            region = futures[future]
            try:
                resources, edges = future.result()
                all_resources.update({item["resource_uid"]: item for item in resources})
                all_edges.update({item["edge_uid"]: item for item in edges})
            except Exception as error:  # isolate unexpected regional failures
                aws._error("discovery", "region", region, "UnhandledError", str(error))

    resources = sorted(
        all_resources.values(), key=lambda item: (item["type"], item["region"], item["arn"])
    )
    edges = sorted(
        all_edges.values(),
        key=lambda item: (item["relation"], item["from_arn"], item["to_arn"]),
    )
    counts: dict[str, int] = {}
    for resource in resources:
        counts[resource["type"]] = counts.get(resource["type"], 0) + 1
    manifest = {
        "schema_version": "1.0",
        "discovered_at": observed_at,
        "account_id": account_id,
        "caller_arn": caller_arn,
        "partition": partition,
        "regions_scanned": sorted(regions),
        "partial": bool(aws.errors) or aws.budget.calls >= aws.budget.maximum,
        "api_calls": aws.budget.calls,
        "summary": {
            "resources": len(resources),
            "edges": len(edges),
            "service_resources": sum(
                count for resource_type, count in counts.items() if resource_type in CORE_SERVICE_TYPES
            ),
            "resource_counts_by_type": dict(sorted(counts.items())),
            "errors": len(aws.errors),
        },
        "resources": resources,
        "edges": edges,
        "errors": sorted(aws.errors, key=lambda item: item["scope"]),
        "limitations": [
            "Control-plane discovery cannot reveal arbitrary application internals.",
            "Missing permissions and API limits produce partial results.",
            "AWS-native metrics marked on resources are configured capabilities, not proof of recent Elastic ingestion.",
            "Kubernetes workloads are not queried without explicit cluster API access.",
            "Environment variable values and secret values are never collected.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
