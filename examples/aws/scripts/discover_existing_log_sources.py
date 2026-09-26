#!/usr/bin/env python3
"""Discover existing AWS CloudWatch and S3-backed log sources."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import shutil
import subprocess
import sys


query = json.load(sys.stdin)
aws_cli = shutil.which("aws") or str(Path.home() / ".local" / "bin" / "aws")
bootstrap_region = query["bootstrap_region"]


def aws(*args: str, timeout: int = 60) -> dict:
    result = subprocess.run(
        [aws_cli, *args, "--output", "json"],
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return json.loads(result.stdout)


def cloudwatch_source(region: str, name: str) -> dict:
    mappings = [
        ("/aws/lambda/", "lambda", "aws.lambda_logs"),
        ("/aws/network-firewall/", "firewall", "aws.firewall_logs"),
        ("aws-waf-logs-", "waf", "aws.waf"),
        ("API-Gateway-Execution-Logs_", "apigateway", "aws.apigateway_logs"),
        ("/aws/elasticmapreduce/", "emr", "aws.emr_logs"),
        ("/aws/route53resolver/", "route53", "aws.route53_resolver_logs"),
        ("/aws/route53/", "route53", "aws.route53_public_logs"),
        ("/aws/ec2/", "ec2", "aws.ec2_logs"),
    ]
    for prefix, template, dataset in mappings:
        if name.startswith(prefix):
            return {
                "kind": "cloudwatch",
                "region": region,
                "log_group_name": name,
                "policy_template": template,
                "input_type": "aws-cloudwatch",
                "dataset": dataset,
            }
    return {
        "kind": "cloudwatch",
        "region": region,
        "log_group_name": name,
        "policy_template": "cloudwatch",
        "input_type": "aws-cloudwatch",
        "dataset": "aws.cloudwatch_logs",
    }


def discover_region(region: str) -> list[dict]:
    try:
        groups = aws(
            "logs",
            "describe-log-groups",
            "--region",
            region,
            timeout=120,
        ).get("logGroups", [])
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []
    return [
        cloudwatch_source(region, group["logGroupName"])
        for group in groups
    ]


def bucket_region(bucket: str) -> str:
    location = aws(
        "s3api",
        "get-bucket-location",
        "--bucket",
        bucket,
    ).get("LocationConstraint")
    return {
        None: "us-east-1",
        "EU": "eu-west-1",
    }.get(location, location)


def s3_source(
    bucket: str,
    prefix: str,
    template: str,
    dataset: str,
) -> dict:
    return {
        "kind": "s3",
        "region": bucket_region(bucket),
        "bucket": bucket,
        "prefix": prefix,
        "policy_template": template,
        "input_type": "aws-s3",
        "dataset": dataset,
    }


regions = aws(
    "ec2",
    "describe-regions",
    "--region",
    bootstrap_region,
    "--all-regions",
)["Regions"]
enabled_regions = [
    item["RegionName"]
    for item in regions
    if item.get("OptInStatus") != "not-opted-in"
]

sources: list[dict] = []
with ThreadPoolExecutor(max_workers=10) as executor:
    futures = [executor.submit(discover_region, region) for region in enabled_regions]
    for future in as_completed(futures):
        sources.extend(future.result())

# Existing S3 server-access logging destinations.
try:
    buckets = [item["Name"] for item in aws("s3api", "list-buckets")["Buckets"]]
except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
    buckets = []


def discover_bucket(bucket: str) -> dict | None:
    try:
        logging = aws(
            "s3api",
            "get-bucket-logging",
            "--bucket",
            bucket,
        ).get("LoggingEnabled")
        if not logging:
            return None
        return s3_source(
            logging["TargetBucket"],
            logging.get("TargetPrefix", ""),
            "s3",
            "aws.s3access",
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


with ThreadPoolExecutor(max_workers=10) as executor:
    futures = [executor.submit(discover_bucket, bucket) for bucket in buckets]
    for future in as_completed(futures):
        source = future.result()
        if source:
            sources.append(source)

# Existing CloudFront standard logging destinations.
try:
    distributions = (
        aws("cloudfront", "list-distributions")
        .get("DistributionList", {})
        .get("Items", [])
    )
    for distribution in distributions:
        logging = distribution.get("Logging", {})
        if not logging.get("Enabled"):
            continue
        bucket = logging["Bucket"].removesuffix(".s3.amazonaws.com")
        sources.append(
            s3_source(
                bucket,
                logging.get("Prefix", ""),
                "cloudfront",
                "aws.cloudfront_logs",
            )
        )
except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
    pass

# Existing ALB/NLB/Classic ELB S3 access-log destinations.
for region in enabled_regions:
    try:
        load_balancers = aws(
            "elbv2",
            "describe-load-balancers",
            "--region",
            region,
        ).get("LoadBalancers", [])
        for load_balancer in load_balancers:
            attributes = aws(
                "elbv2",
                "describe-load-balancer-attributes",
                "--region",
                region,
                "--load-balancer-arn",
                load_balancer["LoadBalancerArn"],
            )["Attributes"]
            values = {item["Key"]: item["Value"] for item in attributes}
            if values.get("access_logs.s3.enabled") != "true":
                continue
            sources.append(
                s3_source(
                    values["access_logs.s3.bucket"],
                    values.get("access_logs.s3.prefix", ""),
                    "elb",
                    "aws.elb_logs",
                )
            )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass

    try:
        classic = aws(
            "elb",
            "describe-load-balancers",
            "--region",
            region,
        ).get("LoadBalancerDescriptions", [])
        for load_balancer in classic:
            name = load_balancer["LoadBalancerName"]
            attributes = aws(
                "elb",
                "describe-load-balancer-attributes",
                "--region",
                region,
                "--load-balancer-name",
                name,
            )["LoadBalancerAttributes"]["AccessLog"]
            if not attributes.get("Enabled"):
                continue
            sources.append(
                s3_source(
                    attributes["S3BucketName"],
                    attributes.get("S3BucketPrefix", ""),
                    "elb",
                    "aws.elb_logs",
                )
            )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass

# De-duplicate sources that share one destination/configuration.
unique = {
    json.dumps(source, sort_keys=True): source
    for source in sources
}
sources = [unique[key] for key in sorted(unique)]
bucket_arns = sorted(
    {
        f"arn:aws:s3:::{source['bucket']}"
        for source in sources
        if source["kind"] == "s3"
    }
)

json.dump(
    {
        "sources_json": json.dumps(sources, sort_keys=True),
        "bucket_arns_json": json.dumps(bucket_arns),
    },
    sys.stdout,
    sort_keys=True,
)
