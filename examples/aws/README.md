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
| Regional security APIs (shared EC2 Agent) | `aws.guardduty`, `aws.securityhub_findings`, `aws.securityhub_findings_full_posture`, `aws.securityhub_insights`, `aws.inspector`, `aws.config` |

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
- every existing CloudWatch log group, mapped to Lambda, Network Firewall,
  WAF, API Gateway, EMR, Route 53, EC2, or generic CloudWatch datasets; and
- existing S3 destinations for ELB access logs, S3 server-access logs, and
  CloudFront standard logs.

Terraform only configures Elastic consumers for sources it discovers. It does
not enable or modify logging on customer Lambda functions, firewalls, load
balancers, buckets, distributions, or other workloads. When customer-side
logging is enabled or disabled, the next apply adds, updates, or removes the
matching Elastic package policy.

## Prerequisites

- Terraform >= 1.2.7
- Python 3 and AWS CLI (used to discover regional GuardDuty detectors)
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

## Authentication is fully bootstrapped

The person running Terraform supplies only the credentials needed to perform
the deployment:

- AWS credentials through the standard Terraform/AWS provider chain; and
- `EC_API_KEY` for Elastic Cloud.

Terraform then configures both runtime authentication paths:

1. **Elastic-managed integrations:** Terraform creates a read-only IAM role,
   configures its trust for Elastic's managed collector, creates the Fleet
   cloud connectors, and selects `identity_federation`.
2. **EC2 Elastic Agent:** Terraform creates and attaches an IAM instance
   profile. The AWS integration uses the default AWS SDK credential chain and
   obtains short-lived credentials from IMDSv2.

Users must not paste an access key, secret key, session token, shared
credentials path, or profile name into any Fleet integration or policy. Those
fields intentionally remain empty after apply.

Regional security discovery uses the same AWS provider environment/profile as
Terraform. It enumerates enabled regions, enables and tags missing GuardDuty
detectors, enables Security Hub/default standards and Inspector where
supported, and creates one merged package policy per region for GuardDuty,
Security Hub CSPM, Inspector, and AWS Config. Running these policies on the
shared EC2 Agent avoids the Serverless managed-runtime limit while retaining
instance-profile/IMDS authentication. The operator enters no region, detector
ID, hub ID, or Fleet credential.

## Apply

### Guided local UI

The [Elastic PoC Deployment Creator](../../tools/aws-poc-ui/README.md) provides
an EUI-based local interface for the workstation that runs Terraform. It
guides credential entry, configuration, preflight checks, plan review, apply,
Workflow execution, and opening the resulting Elastic cockpit. Saved AWS and
Elastic credentials remain on the workstation.

```bash
cd ../../tools/aws-poc-ui
npm ci
npm run build
npm start
```

Then open <http://127.0.0.1:5602>.

### Direct Terraform

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
