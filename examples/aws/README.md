# AWS Observability with one Elastic-managed collector

This example intentionally creates a small, observability-only setup:

- one Elastic **Serverless Observability** project;
- one **Elastic-managed AWS integration** (no EC2-hosted Elastic Agent);
- identity federation through one read-only AWS IAM role; and
- every AWS observability metrics input supported by managed mode, configured
  for **all AWS regions**.

There is no Security project, Cross-Project Search link, Fleet enrollment
token, EC2 collector, CloudTrail/S3/SQS pipeline, CSPM policy, detection-rule
bootstrap, or customer-managed Elastic Agent.

## Enabled integrations

The single managed integration enables these AWS datasets:

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

Log inputs are not enabled: most require a specific regional log group or an
S3/SQS transport and therefore cannot satisfy both the managed-only and
all-regions constraints in a single collector.

## Prerequisites

- Terraform >= 1.2.7
- an Elastic Cloud API key in `EC_API_KEY`
- AWS credentials that can create an IAM role and inline policy
- Elastic Serverless/Kibana 9.5 or later (required by managed integrations)

```bash
export EC_API_KEY="..."
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
```

The IAM role trusts Elastic's managed-collector role and grants only the read
APIs needed by the enabled datasets. No long-lived AWS key is stored in Fleet.

## Apply

```bash
cd examples/aws
cp terraform.tfvars.example terraform.tfvars
# Edit company_tags for your organization.
terraform init
terraform plan
terraform apply
```

After apply, use the `kibana_url` output and verify
`aws-observability-all-regions` under **Fleet → Managed integrations**.

## Cost note

Activating every metrics integration across every region can generate a large
number of CloudWatch API calls. This setup follows the requested broad
coverage; for production, narrow the region lists, increase collection
periods, or add tag filters where appropriate.
