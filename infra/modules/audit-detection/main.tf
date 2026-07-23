data "aws_caller_identity" "current" {}

data "aws_partition" "current" {}

data "aws_region" "current" {}

# Mandate 12: đóng gói ĐÚNG một file thay vì cả thư mục.
#
# source_dir zip mọi thứ trong lambda/, nên __pycache__ có sẵn trên máy chạy
# terraform sẽ lọt vào artifact và làm CodeSha256 lệch baseline mà heartbeat
# so — một FAIL giả, hoặc tệ hơn là che mất một thay đổi code thật. .gitignore
# không giúp được vì archive_file đọc filesystem chứ không đọc git.
#
# Router chỉ import stdlib và boto3 (Lambda runtime có sẵn) nên một file là đủ.
# Nếu sau này tách thêm module, đổi lại source_dir và bổ sung excludes.
data "archive_file" "audit_alert_router" {
  type        = "zip"
  source_file = "${path.module}/lambda/index.py"
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
  sns_topic_arn     = "arn:${data.aws_partition.current.partition}:sns:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:${local.sns_topic_name}"

  # Từ vựng resource của audit plane, cố ý bỏ hậu tố region: một event ở
  # ap-southeast-1 vẫn có thể nhắm vào resource của instance us-east-1.
  # Trail, bucket, router, topic alert, DLQ và 8 rule đều mang một trong hai
  # tiền tố này.
  audit_plane_keywords = distinct(concat(
    [
      lower("${var.cluster_name}-audit-detection"),
      lower("${var.cluster_name}-audit-trail"),
    ],
    [for keyword in var.additional_audit_plane_keywords : lower(keyword)],
  ))
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
    # Nhóm 7 khớp theo eventName trên 5 service và không lọc resource được ở
    # tầng event pattern. Danh sách này là thứ phân biệt "đụng vào audit plane"
    # với "deploy một Lambda bất kỳ": chỉ vế đầu mới alert và mới critical.
    critical_group_7_target_keywords = local.audit_plane_keywords
  })
}

data "aws_iam_policy_document" "audit_kms" {
  statement {
    sid    = "EnableAccountRootPermissions"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = ["arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:root"]
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
      values   = [local.sns_topic_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "kms:EncryptionContext:aws:sns:topicArn"
      values   = [local.sns_topic_arn]
    }
  }

  # Mandate 12: alarm heartbeat publish vào chính topic này, mà topic mã hoá
  # bằng CMK — CloudWatch phải gọi được KMS thì alarm action mới giao được.
  # Chỉ chặn confused deputy bằng aws:SourceAccount: điều kiện hẹp hơn
  # (aws:SourceArn, encryption context) chưa xác nhận được là CloudWatch có
  # điền trong request tới KMS, mà đoán sai ở đây thì hỏng đúng theo kiểu im
  # lặng. Xác nhận bằng set-alarm-state sau apply — xem §Phase 3 execution plan.
  dynamic "statement" {
    for_each = var.cloudwatch_alarm_publisher_enabled ? [1] : []

    content {
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
        values   = [data.aws_caller_identity.current.account_id]
      }
    }
  }

  dynamic "statement" {
    for_each = var.create_trail ? [1] : []

    content {
      sid    = "AllowCloudTrailEncryption"
      effect = "Allow"

      principals {
        type        = "Service"
        identifiers = ["cloudtrail.amazonaws.com"]
      }

      actions = [
        "kms:DescribeKey",
        "kms:GenerateDataKey*",
      ]
      resources = ["*"]

      condition {
        test     = "StringEquals"
        variable = "aws:SourceArn"
        values   = [local.trail_arn]
      }

      condition {
        test     = "StringLike"
        variable = "kms:EncryptionContext:aws:cloudtrail:arn"
        values   = ["arn:${data.aws_partition.current.partition}:cloudtrail:*:${data.aws_caller_identity.current.account_id}:trail/*"]
      }
    }
  }
}

resource "aws_kms_key" "audit" {
  description             = "Audit log and alert encryption for ${local.name_prefix}"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.audit_kms.json
}

resource "aws_kms_alias" "audit" {
  name          = "alias/${local.name_prefix}-audit"
  target_key_id = aws_kms_key.audit.key_id
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
      kms_master_key_id = aws_kms_key.audit.arn
      sse_algorithm     = "aws:kms"
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
  kms_key_id                    = aws_kms_key.audit.arn

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
  name              = local.sns_topic_name
  kms_master_key_id = aws_kms_key.audit.arn
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

# PM-126 exception metadata:
# rule=AVD-AWS-0057
# resource=data.aws_iam_policy_document.audit_alert_router
# reason=CloudWatch Logs authorizes child log streams with the required log-group ARN suffix :*; the actions are limited to CreateLogStream and PutLogEvents.
# owner=tuu-ngo
# ticket=PM-126
# review_date=2026-08-22
#tfsec:ignore:aws-iam-no-policy-wildcards:exp:2026-08-22
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
