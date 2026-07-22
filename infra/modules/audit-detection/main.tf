data "aws_caller_identity" "current" {}

data "aws_partition" "current" {}

data "aws_region" "current" {}

data "archive_file" "audit_alert_router" {
  type        = "zip"
  source_dir  = "${path.module}/lambda"
  output_path = "${path.module}/audit-alert-router.zip"
}

locals {
  name_prefix       = "${var.cluster_name}-audit-detection-${var.deployment_label}"
  trail_name        = "${local.name_prefix}-trail"
  trail_bucket_name = "${var.cluster_name}-audit-trail-${var.deployment_label}-${data.aws_caller_identity.current.account_id}"
  trail_prefix      = "cloudtrail"
  lambda_name       = "${local.name_prefix}-router"
  sns_topic_name    = "${local.name_prefix}-alerts"
  trail_arn         = "arn:${data.aws_partition.current.partition}:cloudtrail:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:trail/${local.trail_name}"
  detector_config = jsonencode({
    deployment_label         = var.deployment_label
    allowed_principals       = var.allowed_automation_principal_arns
    human_principals         = var.human_principal_arns
    secret_reader_principals = var.secret_reader_principal_arns
    sensitive_secret_names   = var.sensitive_secret_names
    suppressions             = var.suppressions
    # Mandate 12: nhóm critical KHÔNG bao giờ bị allowlist automation hoặc
    # suppression làm im lặng. Gồm cả group 3 (leo thang quyền IAM), group 7
    # (tamper alert plane) và group 8 (boundary/OIDC), vì kịch bản phải bắt được
    # là kẻ tấn công dùng chính principal automation đã được tin cậy.
    critical_group_numbers           = [1, 2, 3, 4, 7, 8]
    critical_group_6_target_keywords = ["cloudtrail", "kms", "secret", "rds", "elasticache", "s3"]
  })
}

resource "aws_s3_bucket" "trail_logs" {
  count = var.create_trail ? 1 : 0

  bucket              = local.trail_bucket_name
  object_lock_enabled = true

  # Mandate 12: bucket này là nguồn bằng chứng. Guard chặn plan vô tình
  # replace/delete; nó không thay Object Lock hay IAM boundary.
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "trail_logs" {
  count = var.create_trail ? 1 : 0

  bucket = aws_s3_bucket.trail_logs[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "trail_logs" {
  count = var.create_trail ? 1 : 0

  bucket = aws_s3_bucket.trail_logs[0].id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_object_lock_configuration" "trail_logs" {
  count = var.create_trail ? 1 : 0

  bucket = aws_s3_bucket.trail_logs[0].id

  # Mandate 12: default retention chỉ áp cho object ĐƯỢC GHI SAU khi apply.
  # Object đã giao trước cutover giữ nguyên retention cũ; claim 365 ngày chỉ
  # tính từ UTC cutover đã ghi trong evidence.
  rule {
    default_retention {
      mode = var.trail_object_lock_mode
      days = var.trail_object_lock_days
    }
  }

  depends_on = [aws_s3_bucket_versioning.trail_logs]
}

resource "aws_s3_bucket_server_side_encryption_configuration" "trail_logs" {
  count = var.create_trail ? 1 : 0

  bucket = aws_s3_bucket.trail_logs[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_ownership_controls" "trail_logs" {
  count = var.create_trail ? 1 : 0

  bucket = aws_s3_bucket.trail_logs[0].id

  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "trail_logs" {
  count = var.create_trail ? 1 : 0

  bucket = aws_s3_bucket.trail_logs[0].id

  rule {
    id     = "expire-audit-logs"
    status = "Enabled"

    filter {}

    expiration {
      days = var.trail_s3_retention_days
    }

    noncurrent_version_expiration {
      noncurrent_days = var.trail_s3_retention_days
    }
  }

  # Mandate 12: lifecycle không được xoá object khi Object Lock còn hiệu lực.
  # Nếu retention lifecycle <= Object Lock, S3 để rule fail âm thầm.
  lifecycle {
    precondition {
      condition     = var.trail_s3_retention_days > var.trail_object_lock_days
      error_message = "S3 lifecycle retention must be longer than Object Lock retention."
    }
  }
}

data "aws_iam_policy_document" "trail_logs" {
  count = var.create_trail ? 1 : 0

  statement {
    sid    = "AllowCloudTrailAclCheck"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }

    actions   = ["s3:GetBucketAcl"]
    resources = [aws_s3_bucket.trail_logs[0].arn]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceArn"
      values   = [local.trail_arn]
    }
  }

  statement {
    sid    = "AllowCloudTrailWrite"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }

    actions = ["s3:PutObject"]
    resources = [
      "${aws_s3_bucket.trail_logs[0].arn}/${local.trail_prefix}/AWSLogs/${data.aws_caller_identity.current.account_id}/*",
    ]

    condition {
      test     = "StringEquals"
      variable = "s3:x-amz-acl"
      values   = ["bucket-owner-full-control"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceArn"
      values   = [local.trail_arn]
    }
  }

  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.trail_logs[0].arn,
      "${aws_s3_bucket.trail_logs[0].arn}/*",
    ]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }

  # Mandate 12: chỉ CloudTrail service principal được ghi/sửa object archive.
  # User/role kể cả admin bị chặn put, delete, đổi retention và bypass
  # governance ở tầng resource policy, độc lập với IAM boundary.
  statement {
    sid    = "DenyNonCloudTrailObjectMutation"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions = [
      "s3:AbortMultipartUpload",
      "s3:BypassGovernanceRetention",
      "s3:DeleteObject",
      "s3:DeleteObjectTagging",
      "s3:DeleteObjectVersion",
      "s3:PutObject",
      "s3:PutObjectAcl",
      "s3:PutObjectLegalHold",
      "s3:PutObjectRetention",
      "s3:PutObjectTagging",
      "s3:RestoreObject",
    ]
    resources = ["${aws_s3_bucket.trail_logs[0].arn}/*"]

    condition {
      test     = "StringNotEqualsIfExists"
      variable = "aws:PrincipalServiceName"
      values   = ["cloudtrail.amazonaws.com"]
    }
  }
}

resource "aws_s3_bucket_policy" "trail_logs" {
  count = var.create_trail ? 1 : 0

  bucket = aws_s3_bucket.trail_logs[0].id
  policy = data.aws_iam_policy_document.trail_logs[0].json
}

resource "aws_cloudtrail" "audit" {
  count = var.create_trail ? 1 : 0

  name                          = local.trail_name
  s3_bucket_name                = aws_s3_bucket.trail_logs[0].id
  s3_key_prefix                 = local.trail_prefix
  include_global_service_events = var.include_global_service_events
  is_multi_region_trail         = var.is_multi_region_trail
  enable_logging                = true
  enable_log_file_validation    = true

  # Mandate 12: advanced selectors THAY THẾ basic selector. Phải khai báo lại
  # Management read/write, nếu không sẽ mất toàn bộ coverage của Mandate 11.
  advanced_event_selector {
    name = "ManagementReadWrite"

    field_selector {
      field  = "eventCategory"
      equals = ["Management"]
    }
  }

  # Chỉ bật S3 data events khi owner đã duyệt exact bucket/prefix.
  dynamic "advanced_event_selector" {
    for_each = length(var.s3_data_event_arns) > 0 ? [true] : []

    content {
      name = "ApprovedSensitiveS3Objects"

      field_selector {
        field  = "eventCategory"
        equals = ["Data"]
      }

      field_selector {
        field  = "resources.type"
        equals = ["AWS::S3::Object"]
      }

      field_selector {
        field       = "resources.ARN"
        starts_with = var.s3_data_event_arns
      }
    }
  }

  lifecycle {
    prevent_destroy = true

    # Đưa chính audit archive vào data selector sẽ tạo vòng lặp logging:
    # mỗi lần CloudTrail giao log lại sinh thêm một PutObject data event.
    precondition {
      condition = alltrue([
        for arn in var.s3_data_event_arns :
        !startswith(arn, "${aws_s3_bucket.trail_logs[0].arn}/")
      ])
      error_message = "s3_data_event_arns must not include the audit archive bucket or any of its prefixes."
    }

    # Selector data events chỉ được tạo khi danh sách khác rỗng. Nếu rỗng mà vẫn
    # apply thì trail không ghi GetObject và Mandate 12 trượt đòn "làm hụt" —
    # nhưng plan lại xanh, nên sai sót đó im lặng. Precondition biến nó thành
    # lỗi plan thay vì một gate chỉ nằm trong tài liệu.
    precondition {
      condition     = !var.require_s3_data_event_coverage || length(var.s3_data_event_arns) > 0
      error_message = "Mandate 12: audit_detection_s3_data_event_arns is empty. Fill the data-owner approved S3 ARNs (each ending with /) before planning production."
    }
  }

  depends_on = [aws_s3_bucket_policy.trail_logs]
}

resource "aws_sns_topic" "audit_alerts" {
  name = local.sns_topic_name
}

resource "aws_sns_topic_subscription" "email" {
  for_each = toset(var.alert_email_subscriptions)

  topic_arn = aws_sns_topic.audit_alerts.arn
  protocol  = "email"
  endpoint  = each.value
}

resource "aws_cloudwatch_log_group" "audit_alert_router" {
  name              = "/aws/lambda/${local.lambda_name}"
  retention_in_days = var.lambda_log_retention_days
}

resource "aws_sqs_queue" "audit_alert_router_dlq" {
  name                      = "${local.name_prefix}-lambda-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

data "aws_iam_policy_document" "audit_alert_router_dlq" {
  statement {
    sid    = "AllowLambdaServiceToWriteDlq"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.audit_alert_router_dlq.arn]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_sqs_queue_policy" "audit_alert_router_dlq" {
  queue_url = aws_sqs_queue.audit_alert_router_dlq.id
  policy    = data.aws_iam_policy_document.audit_alert_router_dlq.json
}

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "audit_alert_router" {
  name               = "${local.name_prefix}-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

data "aws_iam_policy_document" "audit_alert_router" {
  statement {
    sid    = "WriteLambdaLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.audit_alert_router.arn}:*"]
  }

  statement {
    sid    = "PublishAlerts"
    effect = "Allow"
    actions = [
      "sns:Publish",
    ]
    resources = [aws_sns_topic.audit_alerts.arn]
  }

  statement {
    sid    = "WriteLambdaDlq"
    effect = "Allow"
    actions = [
      "sqs:SendMessage",
    ]
    resources = [aws_sqs_queue.audit_alert_router_dlq.arn]
  }

  statement {
    sid    = "PublishLatencyMetric"
    effect = "Allow"
    actions = [
      "cloudwatch:PutMetricData",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "audit_alert_router" {
  name   = "${local.name_prefix}-lambda-policy"
  role   = aws_iam_role.audit_alert_router.id
  policy = data.aws_iam_policy_document.audit_alert_router.json
}

resource "aws_lambda_function" "audit_alert_router" {
  function_name    = local.lambda_name
  role             = aws_iam_role.audit_alert_router.arn
  runtime          = "python3.12"
  handler          = "index.handler"
  filename         = data.archive_file.audit_alert_router.output_path
  source_code_hash = data.archive_file.audit_alert_router.output_base64sha256
  timeout          = 30
  memory_size      = 256

  dead_letter_config {
    target_arn = aws_sqs_queue.audit_alert_router_dlq.arn
  }

  environment {
    variables = {
      ALERT_TOPIC_ARN      = aws_sns_topic.audit_alerts.arn
      DETECTOR_CONFIG_JSON = local.detector_config
      METRIC_NAMESPACE     = "TechX/AuditDetection"
      DEPLOYMENT_LABEL     = var.deployment_label
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.audit_alert_router,
    aws_sqs_queue_policy.audit_alert_router_dlq,
  ]
}

resource "aws_cloudwatch_event_rule" "audit" {
  for_each = var.event_rules

  name        = "${local.name_prefix}-${each.key}"
  description = each.value.description
  state       = "ENABLED_WITH_ALL_CLOUDTRAIL_MANAGEMENT_EVENTS"

  event_pattern = jsonencode({
    source        = each.value.sources
    "detail-type" = ["AWS API Call via CloudTrail"]
    detail = {
      eventSource = each.value.event_sources
      eventName   = each.value.event_names
    }
  })
}

resource "aws_cloudwatch_event_target" "audit_alert_router" {
  for_each = aws_cloudwatch_event_rule.audit

  rule      = each.value.name
  target_id = "audit-alert-router"
  arn       = aws_lambda_function.audit_alert_router.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  for_each = aws_cloudwatch_event_rule.audit

  statement_id  = "AllowExecutionFrom${replace(each.key, "-", "")}"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.audit_alert_router.function_name
  principal     = "events.amazonaws.com"
  source_arn    = each.value.arn
}
