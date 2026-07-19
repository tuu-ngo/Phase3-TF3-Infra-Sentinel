locals {
  audit_detection_email_subscriptions = var.audit_detection_email_subscriptions

  audit_detection_human_principal_arns = distinct(concat(
    local.operator_user_arns,
    [local.readonly_user_arn],
    var.audit_detection_additional_human_principal_arns,
  ))

  audit_detection_allowed_automation_principal_arns = distinct(concat(
    [module.eks_platform.external_secrets_role_arn],
    var.audit_detection_additional_allowed_automation_principal_arns,
  ))

  audit_detection_secret_reader_principal_arns = distinct(concat(
    [module.eks_platform.external_secrets_role_arn],
    var.audit_detection_additional_secret_reader_principal_arns,
  ))

  audit_detection_sensitive_secret_names = distinct(concat(
    [module.eks_platform.flagd_sync_secret_name],
    var.audit_detection_additional_sensitive_secret_names,
  ))

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
        "GetSecretValue",
        "BatchGetSecretValue",
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
        "DeleteTrail",
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
  }
}

module "audit_detection_ap_southeast_1" {
  source = "../../modules/audit-detection"

  cluster_name                      = var.cluster_name
  deployment_label                  = var.region
  include_global_service_events     = false
  lambda_log_retention_days         = var.audit_detection_lambda_log_retention_days
  trail_s3_retention_days           = var.audit_detection_trail_s3_retention_days
  alert_email_subscriptions         = local.audit_detection_email_subscriptions
  event_rules                       = local.audit_detection_regional_event_rules
  allowed_automation_principal_arns = local.audit_detection_allowed_automation_principal_arns
  human_principal_arns              = local.audit_detection_human_principal_arns
  secret_reader_principal_arns      = local.audit_detection_secret_reader_principal_arns
  sensitive_secret_names            = local.audit_detection_sensitive_secret_names
  suppressions                      = var.audit_detection_suppressions
}

module "audit_detection_us_east_1" {
  source = "../../modules/audit-detection"

  providers = {
    aws = aws.us_east_1
  }

  cluster_name                      = var.cluster_name
  deployment_label                  = "us-east-1"
  include_global_service_events     = true
  lambda_log_retention_days         = var.audit_detection_lambda_log_retention_days
  trail_s3_retention_days           = var.audit_detection_trail_s3_retention_days
  alert_email_subscriptions         = local.audit_detection_email_subscriptions
  event_rules                       = local.audit_detection_global_event_rules
  allowed_automation_principal_arns = local.audit_detection_allowed_automation_principal_arns
  human_principal_arns              = local.audit_detection_human_principal_arns
  secret_reader_principal_arns      = local.audit_detection_secret_reader_principal_arns
  sensitive_secret_names            = local.audit_detection_sensitive_secret_names
  suppressions                      = var.audit_detection_suppressions
}
