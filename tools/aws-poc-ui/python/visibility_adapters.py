#!/usr/bin/env python3
"""Deploy and roll back narrowly scoped brownfield visibility canaries."""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import urllib.request


STATE_VERSION = "1.0"


def run(command: list[str], *, input_text: str | None = None) -> str:
    print(f"Running {command[0]} {command[1]}", flush=True)
    result = subprocess.run(
        command,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"{command[0]} {command[1]} failed: {detail}")
    return result.stdout


def aws(region: str, *arguments: str) -> dict:
    output = run(["aws", *arguments, "--region", region, "--output", "json"])
    return json.loads(output) if output.strip() else {}


def elastic_request(method: str, path: str, body: dict) -> dict:
    endpoint = os.environ["ELASTICSEARCH_URL"].rstrip("/")
    credentials = base64.b64encode(
        (
            f"{os.environ['ELASTICSEARCH_USERNAME']}:"
            f"{os.environ['ELASTICSEARCH_PASSWORD']}"
        ).encode()
    ).decode()
    request = urllib.request.Request(
        f"{endpoint}{path}",
        data=json.dumps(body).encode(),
        method=method,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def api_key() -> tuple[str, str]:
    result = elastic_request(
        "POST",
        "/_security/api_key",
        {"name": "aws-poc-visibility-canary", "expiration": "30d"},
    )
    encoded = base64.b64encode(
        f"{result['id']}:{result['api_key']}".encode()
    ).decode()
    return result["id"], encoded


def invalidate_api_key(identifier: str) -> None:
    elastic_request("DELETE", "/_security/api_key", {"ids": [identifier]})


def apm_endpoint() -> str:
    endpoint = os.environ["ELASTICSEARCH_URL"]
    if ".es." not in endpoint:
        raise RuntimeError(
            "The Elastic APM intake endpoint could not be derived from the "
            "Elasticsearch endpoint"
        )
    return endpoint.replace(".es.", ".apm.", 1)


def parse_arn(arn: str) -> tuple[str, str]:
    parts = arn.split(":", 5)
    if len(parts) != 6 or not parts[3]:
        raise RuntimeError(f"Unsupported AWS ARN: {arn}")
    return parts[3], parts[5]


def deploy_lambda(proposal: dict) -> dict:
    region, resource = parse_arn(proposal["resource_arn"])
    function_name = resource.removeprefix("function:")
    current = aws(region, "lambda", "get-function-configuration",
                  "--function-name", function_name)
    runtime = current.get("Runtime", "")
    architecture = (current.get("Architectures") or ["x86_64"])[0]
    if not runtime.startswith("python"):
        raise RuntimeError(
            f"Lambda tracing adapter supports Python functions; "
            f"{function_name} uses {runtime or 'an unknown runtime'}"
        )
    if architecture not in {"x86_64", "arm64"}:
        raise RuntimeError(f"Unsupported Lambda architecture: {architecture}")
    layers = [item["Arn"] for item in current.get("Layers", [])]
    agent_layer = (
        f"arn:aws:lambda:{region}:267093732750:"
        "layer:elastic-apm-python-ver-6-26-2:1"
    )
    extension_layer = (
        f"arn:aws:lambda:{region}:267093732750:"
        f"layer:elastic-apm-extension-ver-1-7-1-{architecture}:1"
    )
    variables = dict(current.get("Environment", {}).get("Variables", {}))
    key_id, encoded_key = api_key()
    variables.update(
        {
            "AWS_LAMBDA_EXEC_WRAPPER": "/opt/python/bin/elasticapm-lambda",
            "ELASTIC_APM_LAMBDA_APM_SERVER": apm_endpoint(),
            "ELASTIC_APM_API_KEY": encoded_key,
            "ELASTIC_APM_SEND_STRATEGY": "background",
            "ELASTIC_APM_SERVICE_NAME": function_name,
        }
    )
    try:
        aws(
            region,
            "lambda",
            "update-function-configuration",
            "--function-name",
            function_name,
            "--layers",
            *(layers + [layer for layer in [agent_layer, extension_layer]
                       if layer not in layers]),
            "--environment",
            json.dumps({"Variables": variables}),
        )
        aws(region, "lambda", "wait", "function-updated-v2",
            "--function-name", function_name)
    except Exception:
        try:
            aws(
                region,
                "lambda",
                "update-function-configuration",
                "--cli-input-json",
                json.dumps(
                    {
                        "FunctionName": function_name,
                        "Environment": {
                            "Variables": current.get(
                                "Environment", {}
                            ).get("Variables", {})
                        },
                        "Layers": layers,
                    }
                ),
            )
        except Exception as rollback_error:
            print(f"Automatic Lambda rollback failed: {rollback_error}", flush=True)
        invalidate_api_key(key_id)
        raise
    return {
        "kind": "lambda",
        "region": region,
        "function_name": function_name,
        "layers": layers,
        "environment": current.get("Environment", {}).get("Variables", {}),
        "api_key_id": key_id,
    }


def rollback_lambda(state: dict) -> None:
    aws(
        state["region"],
        "lambda",
        "update-function-configuration",
        "--cli-input-json",
        json.dumps(
            {
                "FunctionName": state["function_name"],
                "Environment": {"Variables": state["environment"]},
                "Layers": state["layers"],
            }
        ),
    )
    invalidate_api_key(state["api_key_id"])


def deploy_rds(proposal: dict) -> dict:
    region, resource = parse_arn(proposal["resource_arn"])
    identifier = resource.split(":", 1)[-1]
    current = aws(
        region,
        "rds",
        "describe-db-instances",
        "--db-instance-identifier",
        identifier,
    )["DBInstances"][0]
    if current.get("PerformanceInsightsEnabled"):
        return {
            "kind": "rds",
            "region": region,
            "identifier": identifier,
            "performance_insights_enabled": True,
            "changed": False,
        }
    aws(
        region,
        "rds",
        "modify-db-instance",
        "--db-instance-identifier",
        identifier,
        "--enable-performance-insights",
        "--apply-immediately",
    )
    return {
        "kind": "rds",
        "region": region,
        "identifier": identifier,
        "performance_insights_enabled": False,
        "changed": True,
    }


def rollback_rds(state: dict) -> None:
    if state["changed"] and not state["performance_insights_enabled"]:
        aws(
            state["region"],
            "rds",
            "modify-db-instance",
            "--db-instance-identifier",
            state["identifier"],
            "--disable-performance-insights",
            "--apply-immediately",
        )


def eks_manifest(namespace: str, endpoint: str, key: str) -> str:
    return f"""apiVersion: v1
kind: Namespace
metadata:
  name: {namespace}
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: elastic-otel-canary
  namespace: {namespace}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: elastic-otel-canary
rules:
- apiGroups: [""]
  resources: [nodes, nodes/stats, pods]
  verbs: [get, list, watch]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: elastic-otel-canary
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: elastic-otel-canary
subjects:
- kind: ServiceAccount
  name: elastic-otel-canary
  namespace: {namespace}
---
apiVersion: v1
kind: Secret
metadata:
  name: elastic-otel-canary
  namespace: {namespace}
stringData:
  api-key: "{key}"
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: elastic-otel-canary
  namespace: {namespace}
data:
  collector.yaml: |
    receivers:
      k8s_cluster:
        collection_interval: 60s
    processors:
      batch: {{}}
    exporters:
      otlp/elastic:
        endpoint: {endpoint.removeprefix("https://")}:443
        headers:
          Authorization: "ApiKey ${{env:ELASTIC_API_KEY}}"
        tls: {{}}
    service:
      pipelines:
        metrics:
          receivers: [k8s_cluster]
          processors: [batch]
          exporters: [otlp/elastic]
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: elastic-otel-canary
  namespace: {namespace}
spec:
  replicas: 1
  selector:
    matchLabels: {{app: elastic-otel-canary}}
  template:
    metadata:
      labels: {{app: elastic-otel-canary}}
    spec:
      serviceAccountName: elastic-otel-canary
      containers:
      - name: collector
        image: otel/opentelemetry-collector-contrib:0.136.0
        args: ["--config=/etc/otel/collector.yaml"]
        env:
        - name: ELASTIC_API_KEY
          valueFrom:
            secretKeyRef:
              name: elastic-otel-canary
              key: api-key
        volumeMounts:
        - name: config
          mountPath: /etc/otel
      volumes:
      - name: config
        configMap:
          name: elastic-otel-canary
"""


def deploy_eks(proposal: dict) -> dict:
    region, resource = parse_arn(proposal["resource_arn"])
    cluster_name = resource.removeprefix("cluster/")
    run(["aws", "eks", "update-kubeconfig", "--name", cluster_name,
         "--region", region])
    namespace = "elastic-poc-canary"
    key_id, encoded_key = api_key()
    manifest = eks_manifest(namespace, apm_endpoint(), encoded_key)
    try:
        run(["kubectl", "apply", "-f", "-"], input_text=manifest)
        run(["kubectl", "-n", namespace, "rollout", "status",
             "deployment/elastic-otel-canary", "--timeout=180s"])
    except Exception:
        run(["kubectl", "delete", "namespace", namespace,
             "--ignore-not-found=true"])
        run(["kubectl", "delete", "clusterrole", "elastic-otel-canary",
             "--ignore-not-found=true"])
        run(["kubectl", "delete", "clusterrolebinding", "elastic-otel-canary",
             "--ignore-not-found=true"])
        invalidate_api_key(key_id)
        raise
    return {"kind": "eks", "region": region, "cluster_name": cluster_name,
            "namespace": namespace, "api_key_id": key_id}


def rollback_eks(state: dict) -> None:
    run(["aws", "eks", "update-kubeconfig", "--name", state["cluster_name"],
         "--region", state["region"]])
    run(["kubectl", "delete", "namespace", state["namespace"],
         "--ignore-not-found=true"])
    run(["kubectl", "delete", "clusterrole", "elastic-otel-canary",
         "--ignore-not-found=true"])
    run(["kubectl", "delete", "clusterrolebinding", "elastic-otel-canary",
         "--ignore-not-found=true"])
    invalidate_api_key(state["api_key_id"])


def deploy_ecs(proposal: dict) -> dict:
    region, resource = parse_arn(proposal["resource_arn"])
    _, cluster, service = resource.split("/", 2)
    current = aws(region, "ecs", "describe-services", "--cluster", cluster,
                  "--services", service)["services"][0]
    if current.get("desiredCount", 0) == 0:
        raise RuntimeError(
            f"ECS service {service} has desired count 0. Start an approved "
            "canary task before enabling application tracing."
        )
    task = aws(region, "ecs", "describe-task-definition",
               "--task-definition", current["taskDefinition"])["taskDefinition"]
    prepared = [
        container for container in task.get("containerDefinitions", [])
        if any(
            item.get("name") in {"ELASTIC_APM_SERVER_URL", "OTEL_EXPORTER_OTLP_ENDPOINT"}
            for item in container.get("environment", [])
        )
    ]
    if not prepared:
        raise RuntimeError(
            f"ECS service {service} does not contain an Elastic APM or OTLP "
            "instrumented container. Add the runtime-specific agent to the "
            "application image; this adapter will then configure its intake."
        )
    raise RuntimeError(
        "ECS intake configuration requires the workload's secret-injection "
        "convention. Configure ELASTIC_APM_API_KEY or OTEL_EXPORTER_OTLP_HEADERS "
        "in the task definition, then retry."
    )


def read_state(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": STATE_VERSION, "adapters": {}}
    return json.loads(path.read_text())


def write_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, delete=False
    ) as handle:
        json.dump(state, handle, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.chmod(0o600)
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["deploy", "rollback"])
    parser.add_argument("--proposal-json", required=True)
    parser.add_argument("--state", type=Path, required=True)
    arguments = parser.parse_args()
    proposal = json.loads(arguments.proposal_json)
    proposal_id = proposal["id"]
    state = read_state(arguments.state)
    if arguments.action == "deploy":
        if proposal_id in state["adapters"]:
            print("Visibility adapter is already deployed", flush=True)
            return 0
        key = (proposal["resource_type"], proposal["signal"])
        adapters = {
            ("aws.lambda.function", "traces"): deploy_lambda,
            ("aws.ecs.service", "traces"): deploy_ecs,
            ("aws.eks.cluster", "metrics"): deploy_eks,
            ("aws.rds.instance", "database"): deploy_rds,
        }
        if key not in adapters:
            raise RuntimeError(f"No adapter exists for {key[0]} {key[1]}")
        state["adapters"][proposal_id] = adapters[key](proposal)
        write_state(arguments.state, state)
        print("Visibility adapter deployed", flush=True)
    else:
        adapter_state = state["adapters"].get(proposal_id)
        if not adapter_state:
            raise RuntimeError("No rollback state exists for this adapter")
        rollback = {
            "lambda": rollback_lambda,
            "eks": rollback_eks,
            "rds": rollback_rds,
        }.get(adapter_state["kind"])
        if not rollback:
            raise RuntimeError(
                f"No rollback adapter exists for {adapter_state['kind']}"
            )
        rollback(adapter_state)
        del state["adapters"][proposal_id]
        write_state(arguments.state, state)
        print("Visibility adapter rolled back", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
