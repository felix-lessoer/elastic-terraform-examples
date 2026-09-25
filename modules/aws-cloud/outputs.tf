output "account_id" {
  value = local.account_id
}

output "region" {
  value = local.region
}

output "logs_bucket_name" {
  value = aws_s3_bucket.logs.bucket
}

output "logs_bucket_arn" {
  value = aws_s3_bucket.logs.arn
}

output "cloudtrail_queue_url" {
  value = aws_sqs_queue.cloudtrail.url
}

output "cloudtrail_queue_arn" {
  value = aws_sqs_queue.cloudtrail.arn
}

output "vpcflow_queue_url" {
  value = try(aws_sqs_queue.vpcflow[0].url, null)
}

output "vpcflow_queue_arn" {
  value = try(aws_sqs_queue.vpcflow[0].arn, null)
}

output "elastic_role_arn" {
  value = aws_iam_role.elastic.arn
}

output "external_id" {
  sensitive = true
  value     = local.external_id
}

output "agent_instance_profile_name" {
  description = "IAM instance profile for Elastic Agent EC2 instances (IMDS credentials)."
  value       = aws_iam_instance_profile.agent.name
}

output "agent_role_arn" {
  value = aws_iam_role.agent.arn
}

output "applied_tags" {
  description = "Tags applied to AWS resources."
  value       = local.common_tags
}
