# Mandate 12 — heartbeat cho audit foundation.
#
# Alert dựa-trên-sự-kiện chỉ kêu khi có event. Nếu kẻ tấn công phá đồng thời
# trail và alert plane thì không còn event nào để kêu. Heartbeat giải quyết đúng
# điểm đó: nó chạy 5 phút/lần, so trạng thái live với cấu hình đã duyệt, và
# publish qua nhiều đường độc lập nên một SNS path hỏng không làm mất tín hiệu.

locals {
  m12_heartbeat_name                = "${var.cluster_name}-m12-audit-heartbeat"
  m12_heartbeat_schedule_name       = "${var.cluster_name}-m12-audit-heartbeat-schedule"
  m12_heartbeat_fallback_topic_name = "${var.cluster_name}-m12-audit-heartbeat-fallback"

  # Dựng ARN topic fallback từ thành phần đã biết. Key policy KMS phải khoá
  # encryption context vào đúng topic này; tham chiếu attribute của chính
  # aws_sns_topic ở đây sẽ tạo cycle topic → key → policy → topic.
  m12_heartbeat_fallback_topic_arn = "arn:aws:sns:${var.region}:${data.aws_caller_identity.m12_current.account_id}:${local.m12_heartbeat_fallback_topic_name}"

  m12_heartbeat_alarm_names = [
    "${var.cluster_name}-m12-audit-heartbeat-missing",
    "${var.cluster_name}-m12-audit-heartbeat-errors",
  ]

  # Heartbeat so cấu hình alarm thật với bảng này. Nếu ai đó nới period,
  # đổi threshold hay bỏ action thì heartbeat FAIL.
  m12_heartbeat_alarm_config = {
    "${local.m12_heartbeat_alarm_names[0]}" = {
      Namespace          = "AWS/Lambda"
      MetricName         = "Invocations"
      Statistic          = "Sum"
      Period             = 900
      EvaluationPeriods  = 1
      DatapointsToAlarm  = 1
      Threshold          = 1
      ComparisonOperator = "LessThanThreshold"
      TreatMissingData   = "breaching"
      Dimensions = {
        FunctionName = local.m12_heartbeat_name
      }
      OKActions               = []
      InsufficientDataActions = []
    }
    "${local.m12_heartbeat_alarm_names[1]}" = {
      Namespace          = "AWS/Lambda"
      MetricName         = "Errors"
      Statistic          = "Sum"
      Period             = 300
      EvaluationPeriods  = 1
      DatapointsToAlarm  = 1
      Threshold          = 1
      ComparisonOperator = "GreaterThanOrEqualToThreshold"
      TreatMissingData   = "notBreaching"
      Dimensions = {
        FunctionName = local.m12_heartbeat_name
      }
      OKActions               = []
      InsufficientDataActions = []
    }
  }

  # Dựng ARN từ thành phần đã biết. Không tham chiếu attribute của chính
  # resource Lambda ở đây, nếu không Terraform báo cycle.
  m12_primary_router_arn     = "arn:aws:lambda:${var.region}:${data.aws_caller_identity.m12_current.account_id}:function:${module.audit_detection_ap_southeast_1.lambda_function_name}"
  m12_global_router_arn      = "arn:aws:lambda:us-east-1:${data.aws_caller_identity.m12_current.account_id}:function:${module.audit_detection_us_east_1.lambda_function_name}"
  m12_heartbeat_function_arn = "arn:aws:lambda:${var.region}:${data.aws_caller_identity.m12_current.account_id}:function:${local.m12_heartbeat_name}"

  # Hai alarm publish vào cả topic M11 primary lẫn fallback cùng region, để một
  # đường hỏng không làm mất tín hiệu. Heartbeat so danh sách này với AlarmActions thật.
  m12_heartbeat_alarm_action_arns = [
    module.audit_detection_ap_southeast_1.sns_topic_arn,
    aws_sns_topic.m12_heartbeat_fallback.arn,
  ]

  m12_heartbeat_alarm_source_arn_pattern = "arn:aws:cloudwatch:${var.region}:${data.aws_caller_identity.m12_current.account_id}:alarm:${var.cluster_name}-m12-audit-heartbeat-*"

  # Trạng thái router đã được duyệt. CI boundary buộc phải cho phép
  # lambda:UpdateFunctionCode (Terraform cần nó để deploy router), nên chặn ở
  # tầng IAM là không khả thi — phát hiện là lớp bù. Heartbeat so bốn field này
  # với Lambda thật; lệch một field là FAIL.
  m12_router_expected = {
    (local.m12_primary_router_arn) = {
      codeSha256     = module.audit_detection_ap_southeast_1.lambda_source_code_hash
      handler        = module.audit_detection_ap_southeast_1.lambda_handler
      roleArn        = module.audit_detection_ap_southeast_1.lambda_role_arn
      detectorConfig = module.audit_detection_ap_southeast_1.lambda_detector_config
    }
    (local.m12_global_router_arn) = {
      codeSha256     = module.audit_detection_us_east_1.lambda_source_code_hash
      handler        = module.audit_detection_us_east_1.lambda_handler
      roleArn        = module.audit_detection_us_east_1.lambda_role_arn
      detectorConfig = module.audit_detection_us_east_1.lambda_detector_config
    }
  }

  m12_primary_rules = {
    for key, rule in local.audit_detection_regional_event_rules :
    "${var.cluster_name}-audit-detection-${var.region}-${key}" => {
      sources       = sort(rule.sources)
      event_sources = sort(rule.event_sources)
      event_names   = sort(rule.event_names)
    }
  }
  m12_global_rules = {
    for key, rule in local.audit_detection_global_event_rules :
    "${var.cluster_name}-audit-detection-us-east-1-${key}" => {
      sources       = sort(rule.sources)
      event_sources = sort(rule.event_sources)
      event_names   = sort(rule.event_names)
    }
  }
}

data "aws_caller_identity" "m12_current" {}

# Topic fallback chở đúng nội dung nhạy cảm như hai topic M11 (chi tiết invariant
# nào của audit plane đang hỏng), nên nó phải được mã hoá bằng CMK giống chúng —
# để plaintext là hạ chuẩn một đường alert so với phần còn lại.
#
# Key riêng chứ không dùng lại key của module M11: key policy M11 khoá encryption
# context đúng vào topic của nó, muốn dùng chung phải nới điều kiện đó trong
# module dùng chung cho cả hai region.
data "aws_iam_policy_document" "m12_heartbeat_fallback_kms" {
  statement {
    sid    = "EnableAccountRootPermissions"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.m12_current.account_id}:root"]
    }

    actions   = ["kms:*"]
    resources = ["*"]
  }

  statement {
    sid    = "AllowSnsEncryption"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["sns.amazonaws.com"]
    }

    actions = [
      "kms:Decrypt",
      "kms:GenerateDataKey",
    ]
    resources = ["*"]

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = [local.m12_heartbeat_fallback_topic_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "kms:EncryptionContext:aws:sns:topicArn"
      values   = [local.m12_heartbeat_fallback_topic_arn]
    }
  }

  # CloudWatch tự gọi KMS khi alarm action publish vào topic mã hoá bằng CMK.
  # Thiếu statement này alarm fail âm thầm — đúng loại hỏng mà heartbeat sinh ra
  # để chặn. Điều kiện SourceAccount trùng với điều kiện đã dùng ở topic policy.
  statement {
    sid    = "AllowCloudWatchAlarmPublish"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com"]
    }

    actions = [
      "kms:Decrypt",
      "kms:GenerateDataKey*",
    ]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.m12_current.account_id]
    }
  }
}

resource "aws_kms_key" "m12_heartbeat_fallback" {
  description             = "Alert encryption for ${local.m12_heartbeat_fallback_topic_name}"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.m12_heartbeat_fallback_kms.json
}

resource "aws_kms_alias" "m12_heartbeat_fallback" {
  name          = "alias/${local.m12_heartbeat_fallback_topic_name}"
  target_key_id = aws_kms_key.m12_heartbeat_fallback.key_id
}

# Fallback cùng region để alarm không phụ thuộc duy nhất vào topic M11 primary.
# Topic global M11 được Lambda dùng trực tiếp, không dùng làm alarm action vì
# CloudWatch alarm chỉ publish được tới SNS cùng region.
resource "aws_sns_topic" "m12_heartbeat_fallback" {
  name              = local.m12_heartbeat_fallback_topic_name
  kms_master_key_id = aws_kms_key.m12_heartbeat_fallback.arn

  lifecycle {
    prevent_destroy = true
  }
}

data "aws_iam_policy_document" "m12_heartbeat_fallback" {
  # Liệt kê tường minh thay vì "sns:*". Topic policy của SNS chỉ nhận các action
  # phạm vi topic; "sns:*" nở ra cả action mức account (CreateTopic, ListTopics,
  # Unsubscribe...) và SetTopicAttributes trả về
  # "InvalidParameter: Policy statement action out of service scope".
  # Đây đúng là danh sách trong default topic policy của AWS.
  statement {
    sid = "AllowAccountManagement"
    actions = [
      "sns:AddPermission",
      "sns:DeleteTopic",
      "sns:GetTopicAttributes",
      "sns:ListSubscriptionsByTopic",
      "sns:Publish",
      "sns:RemovePermission",
      "sns:SetTopicAttributes",
      "sns:Subscribe",
    ]
    resources = [aws_sns_topic.m12_heartbeat_fallback.arn]

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.m12_current.account_id}:root"]
    }
  }

  statement {
    sid       = "AllowCloudWatchAlarmPublish"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.m12_heartbeat_fallback.arn]

    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.m12_current.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = [local.m12_heartbeat_alarm_source_arn_pattern]
    }
  }
}

resource "aws_sns_topic_policy" "m12_heartbeat_fallback" {
  arn    = aws_sns_topic.m12_heartbeat_fallback.arn
  policy = data.aws_iam_policy_document.m12_heartbeat_fallback.json
}

# Topic primary của M11 chưa có policy cho service principal CloudWatch. Thiếu
# nó, alarm action sẽ fail âm thầm. Thêm ở production root vì đây là nơi sở hữu
# alarm; module M11 giữ nguyên.
data "aws_iam_policy_document" "m12_primary_alarm_topic" {
  # Cùng lý do như topic fallback: "sns:*" bị SNS từ chối vì lọt action ngoài
  # phạm vi topic.
  statement {
    sid = "AllowAccountManagement"
    actions = [
      "sns:AddPermission",
      "sns:DeleteTopic",
      "sns:GetTopicAttributes",
      "sns:ListSubscriptionsByTopic",
      "sns:Publish",
      "sns:RemovePermission",
      "sns:SetTopicAttributes",
      "sns:Subscribe",
    ]
    resources = [module.audit_detection_ap_southeast_1.sns_topic_arn]

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.m12_current.account_id}:root"]
    }
  }

  statement {
    sid       = "AllowCloudWatchAlarmPublish"
    actions   = ["sns:Publish"]
    resources = [module.audit_detection_ap_southeast_1.sns_topic_arn]

    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.m12_current.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = [local.m12_heartbeat_alarm_source_arn_pattern]
    }
  }
}

resource "aws_sns_topic_policy" "m12_primary_alarm_topic" {
  arn    = module.audit_detection_ap_southeast_1.sns_topic_arn
  policy = data.aws_iam_policy_document.m12_primary_alarm_topic.json
}

resource "aws_sns_topic_subscription" "m12_heartbeat_fallback_email" {
  for_each = toset(local.audit_detection_email_subscriptions)

  topic_arn = aws_sns_topic.m12_heartbeat_fallback.arn
  protocol  = "email"
  endpoint  = each.value
}

# source_file (không phải source_dir) và thư mục lambda-heartbeat/ riêng: nếu
# đặt heartbeat.py trong modules/audit-detection/lambda/ thì nó lọt vào
# audit-alert-router.zip và làm router redeploy mỗi lần sửa heartbeat.
data "archive_file" "m12_audit_heartbeat" {
  type        = "zip"
  source_file = "${path.module}/../../modules/audit-detection/lambda-heartbeat/heartbeat.py"
  output_path = "${path.module}/m12-audit-heartbeat.zip"
}

data "aws_iam_policy_document" "m12_heartbeat_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "m12_audit_heartbeat" {
  name               = local.m12_heartbeat_name
  assume_role_policy = data.aws_iam_policy_document.m12_heartbeat_assume.json
}

# PM-126 exception metadata:
# rule=AVD-AWS-0057
# resource=data.aws_iam_policy_document.m12_audit_heartbeat
# reason=Heartbeat chỉ đọc, không có action nào mutate. ReadAuditHealth phải để Resource "*" vì cloudwatch:DescribeAlarms và cloudtrail:DescribeTrails không hỗ trợ resource-level permission; WriteHeartbeatLogs dùng đúng hậu tố log-group ":*" mà CloudWatch Logs bắt buộc để địa chỉ hoá child stream.
# owner=tuu-ngo
# ticket=PM-126
# review_date=2026-08-22
#tfsec:ignore:aws-iam-no-policy-wildcards:exp:2026-08-22
data "aws_iam_policy_document" "m12_audit_heartbeat" {
  statement {
    sid = "ReadAuditHealth"
    actions = [
      "cloudtrail:GetEventSelectors",
      "cloudtrail:GetTrailStatus",
      "cloudtrail:DescribeTrails",
      "events:DescribeRule",
      "events:ListTargetsByRule",
      "lambda:GetFunctionConfiguration",
      "lambda:GetFunctionConcurrency",
      "cloudwatch:DescribeAlarms",
      "s3:GetBucketEncryption",
      "s3:GetBucketLifecycleConfiguration",
      "s3:GetBucketPolicy",
      "s3:GetBucketPolicyStatus",
      "s3:GetBucketPublicAccessBlock",
      "s3:GetBucketVersioning",
      "s3:GetObjectLockConfiguration",
      "sns:GetTopicAttributes",
      "sns:ListSubscriptionsByTopic",
      "eks:DescribeCluster",
      # Xác nhận permissions boundary còn attach. Cần thiết vì với
      # gitlab-ci-deployer việc attach là thủ công, không có gì cưỡng chế.
      "iam:GetRole",
      "iam:GetUser"
    ]
    resources = ["*"]
  }

  statement {
    sid     = "PublishAuditAlert"
    actions = ["sns:Publish"]
    resources = [
      module.audit_detection_ap_southeast_1.sns_topic_arn,
      module.audit_detection_us_east_1.sns_topic_arn,
    ]
  }

  # Cả hai topic M11 mã hoá bằng CMK riêng của từng region, nên sns:Publish
  # không đủ — publisher phải gọi được KMS. Đúng lỗi đã làm sập luồng alert của
  # router M11; heartbeat publish vào chính hai topic đó nên dính y hệt.
  statement {
    sid = "EncryptAuditAlert"
    actions = [
      "kms:Decrypt",
      "kms:GenerateDataKey*",
    ]
    resources = [
      module.audit_detection_ap_southeast_1.kms_key_arn,
      module.audit_detection_us_east_1.kms_key_arn,
    ]
  }

  statement {
    sid = "WriteHeartbeatLogs"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = ["${aws_cloudwatch_log_group.m12_audit_heartbeat.arn}:*"]
  }
}

resource "aws_iam_role_policy" "m12_audit_heartbeat" {
  name   = local.m12_heartbeat_name
  role   = aws_iam_role.m12_audit_heartbeat.id
  policy = data.aws_iam_policy_document.m12_audit_heartbeat.json
}

resource "aws_cloudwatch_log_group" "m12_audit_heartbeat" {
  name              = "/aws/lambda/${local.m12_heartbeat_name}"
  retention_in_days = 90
}

resource "aws_lambda_function" "m12_audit_heartbeat" {
  function_name    = local.m12_heartbeat_name
  role             = aws_iam_role.m12_audit_heartbeat.arn
  runtime          = "python3.12"
  handler          = "heartbeat.handler"
  filename         = data.archive_file.m12_audit_heartbeat.output_path
  source_code_hash = data.archive_file.m12_audit_heartbeat.output_base64sha256
  timeout          = 60
  memory_size      = 256

  environment {
    variables = {
      TRAIL_NAME                           = module.audit_detection_ap_southeast_1.trail_name
      AUDIT_BUCKET_NAME                    = module.audit_detection_ap_southeast_1.trail_bucket_name
      ALERT_TOPIC_ARN                      = module.audit_detection_ap_southeast_1.sns_topic_arn
      FALLBACK_ALERT_TOPIC_ARN             = aws_sns_topic.m12_heartbeat_fallback.arn
      GLOBAL_ALERT_TOPIC_ARN               = module.audit_detection_us_east_1.sns_topic_arn
      PRIMARY_REGION                       = var.region
      GLOBAL_REGION                        = "us-east-1"
      PRIMARY_RULES_JSON                   = jsonencode(local.m12_primary_rules)
      GLOBAL_RULES_JSON                    = jsonencode(local.m12_global_rules)
      PRIMARY_ROUTER_ARN                   = local.m12_primary_router_arn
      GLOBAL_ROUTER_ARN                    = local.m12_global_router_arn
      ROUTER_EXPECTED_JSON                 = jsonencode(local.m12_router_expected)
      BOUNDED_PRINCIPALS_JSON              = jsonencode(var.audit_detection_bounded_principals)
      HEARTBEAT_SCHEDULE_RULE_NAME         = local.m12_heartbeat_schedule_name
      HEARTBEAT_FUNCTION_ARN               = local.m12_heartbeat_function_arn
      HEARTBEAT_ALARM_NAMES_JSON           = jsonencode(local.m12_heartbeat_alarm_names)
      HEARTBEAT_ALARM_CONFIG_JSON          = jsonencode(local.m12_heartbeat_alarm_config)
      HEARTBEAT_ALARM_ACTION_ARNS_JSON     = jsonencode(local.m12_heartbeat_alarm_action_arns)
      HEARTBEAT_ALARM_SOURCE_ARN_PATTERN   = local.m12_heartbeat_alarm_source_arn_pattern
      EXPECTED_SUBSCRIPTION_ENDPOINTS_JSON = jsonencode(local.audit_detection_email_subscriptions)
      S3_DATA_EVENT_ARNS_JSON              = jsonencode(var.audit_detection_s3_data_event_arns)
      MAX_LOG_DELIVERY_AGE_MINUTES         = "20"
      MAX_DIGEST_DELIVERY_AGE_MINUTES      = "90"
      REQUIRED_RETENTION_DAYS              = tostring(var.audit_detection_trail_object_lock_days)
      REQUIRED_LIFECYCLE_DAYS              = tostring(var.audit_detection_trail_s3_retention_days)
      EKS_CLUSTER_NAME                     = var.cluster_name
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.m12_audit_heartbeat,
    aws_iam_role_policy.m12_audit_heartbeat
  ]
}

resource "aws_cloudwatch_event_rule" "m12_audit_heartbeat" {
  name                = local.m12_heartbeat_schedule_name
  description         = "Run Mandate 12 audit heartbeat every five minutes."
  schedule_expression = "rate(5 minutes)"
  state               = "ENABLED"
}

resource "aws_cloudwatch_event_target" "m12_audit_heartbeat" {
  rule      = aws_cloudwatch_event_rule.m12_audit_heartbeat.name
  target_id = "m12-audit-heartbeat"
  arn       = aws_lambda_function.m12_audit_heartbeat.arn
}

resource "aws_lambda_permission" "m12_audit_heartbeat" {
  statement_id  = "AllowExecutionFromM12HeartbeatSchedule"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.m12_audit_heartbeat.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.m12_audit_heartbeat.arn
}

# Heartbeat chạy 5 phút/lần nên 15 phút phải có ít nhất 3 invocation.
# treat_missing_data = breaching: không có datapoint cũng là mất tín hiệu.
resource "aws_cloudwatch_metric_alarm" "m12_audit_heartbeat_missing" {
  alarm_name          = local.m12_heartbeat_alarm_names[0]
  namespace           = "AWS/Lambda"
  metric_name         = "Invocations"
  statistic           = "Sum"
  period              = 900
  evaluation_periods  = 1
  datapoints_to_alarm = 1
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"
  alarm_actions       = local.m12_heartbeat_alarm_action_arns

  dimensions = {
    FunctionName = aws_lambda_function.m12_audit_heartbeat.function_name
  }

  depends_on = [
    aws_sns_topic_policy.m12_primary_alarm_topic,
    aws_sns_topic_policy.m12_heartbeat_fallback,
  ]
}

resource "aws_cloudwatch_metric_alarm" "m12_audit_heartbeat_errors" {
  alarm_name          = local.m12_heartbeat_alarm_names[1]
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  datapoints_to_alarm = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.m12_heartbeat_alarm_action_arns

  dimensions = {
    FunctionName = aws_lambda_function.m12_audit_heartbeat.function_name
  }

  depends_on = [
    aws_sns_topic_policy.m12_primary_alarm_topic,
    aws_sns_topic_policy.m12_heartbeat_fallback,
  ]
}

output "m12_audit_heartbeat_function_arn" {
  value = aws_lambda_function.m12_audit_heartbeat.arn
}

output "m12_audit_heartbeat_schedule_rule_arn" {
  value = aws_cloudwatch_event_rule.m12_audit_heartbeat.arn
}

output "m12_audit_heartbeat_alarm_arns" {
  value = [
    aws_cloudwatch_metric_alarm.m12_audit_heartbeat_missing.arn,
    aws_cloudwatch_metric_alarm.m12_audit_heartbeat_errors.arn,
  ]
}

output "m12_heartbeat_fallback_topic_arn" {
  value = aws_sns_topic.m12_heartbeat_fallback.arn
}
