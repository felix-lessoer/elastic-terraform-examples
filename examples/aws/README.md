# AWS Observability with managed collection and one EC2 agent

This example intentionally creates a small, observability-only setup:

- one Elastic **Serverless Observability** project;
- one **Elastic-managed AWS integration** for every supported input;
- one EC2-hosted Elastic Agent for integrations unavailable in managed mode;
- identity federation through one read-only AWS IAM role; and
- every AWS observability metrics input supported by managed mode, configured
  for **all AWS regions**;
- the pinned AWS Observability cockpit dashboard; and
- pinned Kibana workflows from `examples/aws/workflows`.

There is no Security project, Cross-Project Search link, CSPM policy, or
detection-rule bootstrap. Dashboards and workflows remain in the Observability
project. Terraform provisions CloudTrail and VPC Flow Log S3/SQS sources for
the agent-only log streams.

## Enabled integrations

The managed policies enable these AWS datasets:

| Service | Dataset |
| --- | --- |
| AWS Health | `aws.awshealth` |
| Billing | `aws.billing` |
| CloudWatch | `aws.cloudwatch_metrics` |
| DynamoDB | `aws.dynamodb` |
| EBS | `aws.ebs` |
| EC2 | `aws.ec2_metrics` |
| ECS | `aws.ecs_metrics` |
| ELB | `aws.elb_metrics` |
| Lambda | `aws.lambda` |
| Network Firewall | `aws.firewall_metrics` |
| RDS | `aws.rds` |
| S3 | `aws.s3_daily_storage`, `aws.s3_request` |
| SNS | `aws.sns` |
| SQS | `aws.sqs` |
| Transit Gateway | `aws.transitgateway` |

Each regional metrics stream sets `regions = []`. In the Elastic AWS
integration, an empty region selection means that the collector discovers and
queries every enabled AWS region. Billing is a global API and has no region
selector.

Log inputs generally require a specific regional log group or an S3/SQS
transport and therefore cannot satisfy the all-regions constraint in the
managed collector. They are assigned to the EC2 agent instead.

## EC2 agent collection

The EC2 agent enables all metric streams from policy templates that do not
offer managed mode:

- NAT Gateway
- S3 Storage Lens
- AWS Usage
- VPN
- Redshift
- Kinesis Data Streams
- API Gateway metrics
- EMR metrics
- Amazon MSK metrics

All of these metrics streams use `regions = []`, which enables discovery
across every AWS region.

The agent also collects:

- multi-region CloudTrail through a Terraform-created S3/SQS source, or by
  polling `existing_cloudtrail_bucket_name` when the account trail quota is
  already exhausted;
- VPC Flow Logs for the default VPC in `aws_region` through S3/SQS;
- WAF, Route 53, API Gateway, and EMR logs from their standard CloudWatch log
  group prefixes in `aws_region` (Route 53 public query logs use `us-east-1`);
- CloudFront logs when `cloudfront_queue_url` points to an existing SQS queue
  receiving S3 object notifications.

CloudFront cannot be auto-wired without knowing the distribution's logging
bucket. Likewise, existing resources must already deliver WAF, Route 53,
API Gateway, and EMR logs to the standard CloudWatch groups; enabling an input
does not turn on logging for those AWS services.

## Prerequisites

- Terraform >= 1.2.7
- an Elastic Cloud API key in `EC_API_KEY`
- AWS credentials that can create IAM, EC2, S3, SQS, CloudTrail, and VPC Flow
  Log resources
- Elastic Serverless/Kibana 9.5 or later (required by managed integrations)

```bash
export EC_API_KEY="..."
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
```

The managed integration uses a federated IAM role. The EC2 agent uses an
instance profile and IMDS. No long-lived AWS key is stored in Fleet.

## Apply

```bash
cd examples/aws
cp terraform.tfvars.example terraform.tfvars
# Edit company_tags for your organization.
terraform init
terraform plan
terraform apply
```

After apply:

1. Use `kibana_url` and verify the `aws-managed-*-all-regions` policies under
   **Fleet → Managed integrations**.
2. Confirm the EC2 collector is healthy under **Fleet → Agents**.
3. Open `cockpit_dashboard_url`; package-provided AWS dashboards are also
   installed automatically.
4. Check `workflow_ids` for the pinned YAML definitions deployed from
   `examples/aws/workflows`.

## Cost note

Activating every metrics integration across every region can generate a large
number of CloudWatch API calls. This setup follows the requested broad
coverage; for production, narrow the region lists, increase collection
periods, or add tag filters where appropriate.
