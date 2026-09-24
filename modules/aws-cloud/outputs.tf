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

output "elastic_role_arn" {
  value = aws_iam_role.elastic.arn
}

output "external_id" {
  sensitive = true
  value     = local.external_id
}
