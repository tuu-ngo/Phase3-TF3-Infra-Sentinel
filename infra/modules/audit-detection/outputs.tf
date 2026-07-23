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

# Mandate 12: heartbeat so bốn giá trị này với trạng thái Lambda thật. Kiểm tra
# State=Active là chưa đủ — router có thể bị thay code thành no-op mà vẫn Active,
# khi đó alert bị nuốt trong im lặng. detector_config nằm trong danh sách vì đó
# là nơi chứa critical_group_numbers; sửa nó là cách gỡ bypass allowlist.
output "lambda_source_code_hash" {
  value = aws_lambda_function.audit_alert_router.source_code_hash
}

output "lambda_handler" {
  value = aws_lambda_function.audit_alert_router.handler
}

output "lambda_role_arn" {
  value = aws_lambda_function.audit_alert_router.role
}

output "lambda_detector_config" {
  value = local.detector_config
}
