# Mandate #1 - Auditability: record WHO accesses the operational entrypoint
# (the SSM bastion, which is the only private path to Grafana/Jaeger/ArgoCD) and
# WHEN, by streaming every Session Manager session to CloudWatch Logs.
#
# The bastion is the single door to the private EKS API; logging its sessions is
# how we satisfy the mandate's "ghi lại ai truy cập cổng vận hành, khi nào".

resource "aws_cloudwatch_log_group" "ssm_sessions" {
  name              = "/${var.cluster_name}/ssm-session-logs"
  retention_in_days = 30
}

# Account/region Session Manager preferences. "SSM-SessionManagerRunShell" is the
# reserved document name Session Manager reads its preferences from; setting
# cloudWatchStreamingEnabled makes every session stream to the group above.
resource "aws_ssm_document" "session_preferences" {
  name            = "SSM-SessionManagerRunShell"
  document_type   = "Session"
  document_format = "JSON"

  content = jsonencode({
    schemaVersion = "1.0"
    description   = "Session Manager preferences - log ops-access sessions to CloudWatch (Mandate #1 auditability)"
    sessionType   = "Standard_Stream"
    inputs = {
      cloudWatchLogGroupName      = aws_cloudwatch_log_group.ssm_sessions.name
      cloudWatchEncryptionEnabled = false
      cloudWatchStreamingEnabled  = true
      idleSessionTimeout          = "20"
      runAsEnabled                = false
      shellProfile = {
        linux = ""
      }
    }
  })
}

# Let the bastion write its session logs to the group above. (Its base role only
# has AmazonSSMManagedInstanceCore, which does not include these log actions.)
resource "aws_iam_role_policy" "bastion_session_logs" {
  name = "ssm-session-cloudwatch-logs"
  role = aws_iam_role.bastion.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:DescribeLogStreams",
      ]
      Resource = "${aws_cloudwatch_log_group.ssm_sessions.arn}:*"
    }]
  })
}

output "ssm_session_log_group" {
  description = "CloudWatch Logs group with the audit trail of ops-access (SSM bastion) sessions"
  value       = aws_cloudwatch_log_group.ssm_sessions.name
}
