output "trail_name" {
  value = try(aws_cloudtrail.audit[0].name, null)
}

output "trail_bucket_name" {
  value = try(aws_s3_bucket.trail_logs[0].bucket, null)
}

output "lambda_function_name" {
  value = aws_lambda_function.audit_alert_router.function_name
}

output "sns_topic_arn" {
  value = aws_sns_topic.audit_alerts.arn
}

output "event_rule_names" {
  value = keys(var.event_rules)
}
