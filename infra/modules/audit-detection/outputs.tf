output "trail_name" {
  value = aws_cloudtrail.audit.name
}

output "trail_bucket_name" {
  value = aws_s3_bucket.trail_logs.bucket
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
