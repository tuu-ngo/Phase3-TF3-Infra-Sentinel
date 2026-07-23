locals {
  audit_detection_email_subscriptions = var.audit_detection_email_subscriptions

  # Resource heartbeat M12 nằm ở root này chứ không ở module, nên module không
  # tự suy ra được. Một tiền tố phủ đủ: function, schedule rule, 2 alarm và
  # topic fallback đều bắt đầu bằng nó.
  audit_detection_extra_audit_plane_keywords = ["${var.cluster_name}-m12-audit-heartbeat"]

  audit_detection_human_principal_arns = distinct(concat(
    local.operator_user_arns,
    [local.readonly_user_arn],
    var.audit_detection_additional_human_principal_arns,
  ))

  audit_detection_allowed_automation_principal_arns = distinct(concat(
    [
      module.eks_platform.external_secrets_role_arn,
      "arn:aws:iam::${data.aws_caller_identity.production_access.account_id}:role/techx-corp-tf3-gha-terraform-plan",
      "arn:aws:iam::${data.aws_caller_identity.production_access.account_id}:role/techx-corp-tf3-gha-terraform-apply",
    ],
    var.audit_detection_additional_allowed_automation_principal_arns,
  ))

  audit_detection_secret_reader_principal_arns = distinct(concat(
    [module.eks_platform.external_secrets_role_arn],
    var.audit_detection_additional_secret_reader_principal_arns,
  ))

  audit_detection_sensitive_secret_names = distinct(compact(concat(
    [module.eks_platform.flagd_sync_secret_name],
    var.enable_managed_datastores ? [
      "rds!db-",
      "${var.datastores_name_prefix}/elasticache-auth",
      "AmazonMSK_${var.datastores_name_prefix}/kafka-scram",
    ] : [],
    var.audit_detection_additional_sensitive_secret_names,
  )))

  audit_detection_regional_event_rules = {
    g1-audit = {
      description   = "Group 1: detect actions that blind audit visibility in ap-southeast-1."
      sources       = ["aws.cloudtrail", "aws.logs"]
      event_sources = ["cloudtrail.amazonaws.com", "logs.amazonaws.com"]
      event_names = [
        "StopLogging",
        "DeleteTrail",
        "UpdateTrail",
        "PutEventSelectors",
        "StartLogging",
        "DeleteLogGroup",
        "PutRetentionPolicy",
      ]
    }
    g4-eks = {
      description   = "Group 4: detect EKS access-path changes in ap-southeast-1."
      sources       = ["aws.eks"]
      event_sources = ["eks.amazonaws.com"]
      event_names = [
        "CreateAccessEntry",
        "UpdateAccessEntry",
        "DeleteAccessEntry",
        "AssociateAccessPolicy",
        "DisassociateAccessPolicy",
      ]
    }
    g5-secrets = {
      description   = "Group 5: detect sensitive secret reads in ap-southeast-1."
      sources       = ["aws.secretsmanager"]
      event_sources = ["secretsmanager.amazonaws.com"]
      event_names = [
        "BatchGetSecretValue",
        "GetSecretValue",
      ]
    }
    g6-destroy = {
      description   = "Group 6: detect destructive actions against runtime and recovery paths in ap-southeast-1."
      sources       = ["aws.eks", "aws.rds", "aws.elasticache", "aws.kms", "aws.secretsmanager", "aws.s3", "aws.cloudtrail"]
      event_sources = ["eks.amazonaws.com", "rds.amazonaws.com", "elasticache.amazonaws.com", "kms.amazonaws.com", "secretsmanager.amazonaws.com", "s3.amazonaws.com", "cloudtrail.amazonaws.com"]
      event_names = [
        "DeleteCluster",
        "DeleteNodegroup",
        "DeleteDBInstance",
        "DeleteDBCluster",
        "DeleteReplicationGroup",
        "DeleteCacheCluster",
        "ScheduleKeyDeletion",
        "DeleteSecret",
        "DeleteBucket",
      ]
    }
    # Mandate 12 — Group 7: bảo vệ chính alert plane và heartbeat.
    # Với CloudWatch API qua CloudTrail, cặp đúng là source = aws.monitoring và
    # detail.eventSource = monitoring.amazonaws.com. KHÔNG dùng aws.cloudwatch:
    # pattern sẽ không khớp và rule im lặng. Heartbeat có invariant suy source
    # từ eventSource nên cấu hình sai không thể tự xác nhận PASS.
    g7-audit-controls = {
      description = "Group 7: detect mutation of the M11/M12 alert and heartbeat controls."
      sources = [
        "aws.events", "aws.sns", "aws.lambda", "aws.monitoring", "aws.s3"
      ]
      event_sources = [
        "events.amazonaws.com", "sns.amazonaws.com", "lambda.amazonaws.com",
        "monitoring.amazonaws.com", "s3.amazonaws.com"
      ]
      event_names = [
        "DisableRule", "DeleteRule", "PutRule", "RemoveTargets", "PutTargets",
        "AddPermission", "RemovePermission", "DeleteTopic", "SetTopicAttributes",
        "Subscribe", "ConfirmSubscription", "SetSubscriptionAttributes", "Unsubscribe",
        "DeleteFunction", "UpdateFunctionCode", "UpdateFunctionConfiguration",
        "PutFunctionConcurrency", "DeleteFunctionConcurrency",
        "DeleteAlarms", "DisableAlarmActions", "PutMetricAlarm",
        "PutBucketPolicy", "DeleteBucketPolicy", "PutBucketVersioning",
        "PutObjectLockConfiguration", "PutBucketLifecycleConfiguration",
        "DeleteBucketLifecycle", "PutBucketEncryption", "DeleteBucketEncryption",
        "PutPublicAccessBlock", "DeletePublicAccessBlock"
      ]
    }
  }

  audit_detection_global_event_rules = {
    g2-new-access = {
      description   = "Group 2: detect IAM actions that create new access paths in us-east-1."
      sources       = ["aws.iam"]
      event_sources = ["iam.amazonaws.com"]
      event_names = [
        "CreateAccessKey",
        "CreateUser",
        "CreateRole",
        "CreateLoginProfile",
      ]
    }
    g3-privilege = {
      description   = "Group 3: detect IAM privilege expansion in us-east-1."
      sources       = ["aws.iam"]
      event_sources = ["iam.amazonaws.com"]
      event_names = [
        "UpdateAssumeRolePolicy",
        "AttachUserPolicy",
        "AttachRolePolicy",
        "PutUserPolicy",
        "PutRolePolicy",
        "CreatePolicyVersion",
        "SetDefaultPolicyVersion",
        "AddUserToGroup",
        "UpdateUser",
      ]
    }
    # Mandate 12 — Group 8: boundary, policy attachment và trust path OIDC.
    # Chạy ở us-east-1 vì IAM là global service, CloudTrail ghi event ở đó.
    g8-iam-controls = {
      description   = "Group 8: detect permissions-boundary, policy and OIDC trust-path tampering."
      sources       = ["aws.iam"]
      event_sources = ["iam.amazonaws.com"]
      event_names = [
        "PutUserPermissionsBoundary", "DeleteUserPermissionsBoundary",
        "PutRolePermissionsBoundary", "DeleteRolePermissionsBoundary",
        "DeletePolicy", "DeletePolicyVersion", "DeleteUserPolicy", "DeleteRolePolicy",
        "DetachUserPolicy", "DetachRolePolicy",
        "CreateOpenIDConnectProvider", "DeleteOpenIDConnectProvider",
        "UpdateOpenIDConnectProviderThumbprint",
        "AddClientIDToOpenIDConnectProvider", "RemoveClientIDFromOpenIDConnectProvider"
      ]
    }
  }
}

module "audit_detection_ap_southeast_1" {
  source = "../../modules/audit-detection"

  cluster_name                  = var.cluster_name
  deployment_label              = var.region
  create_trail                  = true
  include_global_service_events = true
  is_multi_region_trail         = true
  lambda_log_retention_days     = var.audit_detection_lambda_log_retention_days
  trail_s3_retention_days       = var.audit_detection_trail_s3_retention_days
  # Mandate 12 — chỉ instance tạo trail mới nhận các input này.
  # require_s3_data_event_coverage = true: plan FAIL nếu chưa điền ARN đã duyệt,
  # thay vì apply một trail không ghi GetObject.
  trail_object_lock_mode         = var.audit_detection_trail_object_lock_mode
  trail_object_lock_days         = var.audit_detection_trail_object_lock_days
  s3_data_event_arns             = var.audit_detection_s3_data_event_arns
  require_s3_data_event_coverage = true
  # Chỉ instance này có alarm heartbeat trỏ vào topic của nó.
  cloudwatch_alarm_publisher_enabled = true
  additional_audit_plane_keywords    = local.audit_detection_extra_audit_plane_keywords
  alert_email_subscriptions          = local.audit_detection_email_subscriptions
  event_rules                        = local.audit_detection_regional_event_rules
  allowed_automation_principal_arns  = local.audit_detection_allowed_automation_principal_arns
  human_principal_arns               = local.audit_detection_human_principal_arns
  secret_reader_principal_arns       = local.audit_detection_secret_reader_principal_arns
  sensitive_secret_names             = local.audit_detection_sensitive_secret_names
  suppressions                       = var.audit_detection_suppressions
}

module "audit_detection_us_east_1" {
  source = "../../modules/audit-detection"

  providers = {
    aws = aws.us_east_1
  }

  cluster_name                      = var.cluster_name
  deployment_label                  = "us-east-1"
  create_trail                      = false
  include_global_service_events     = false
  is_multi_region_trail             = false
  lambda_log_retention_days         = var.audit_detection_lambda_log_retention_days
  trail_s3_retention_days           = var.audit_detection_trail_s3_retention_days
  additional_audit_plane_keywords   = local.audit_detection_extra_audit_plane_keywords
  alert_email_subscriptions         = local.audit_detection_email_subscriptions
  event_rules                       = local.audit_detection_global_event_rules
  allowed_automation_principal_arns = local.audit_detection_allowed_automation_principal_arns
  human_principal_arns              = local.audit_detection_human_principal_arns
  secret_reader_principal_arns      = local.audit_detection_secret_reader_principal_arns
  sensitive_secret_names            = local.audit_detection_sensitive_secret_names
  suppressions                      = var.audit_detection_suppressions
}
