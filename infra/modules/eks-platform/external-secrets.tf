locals {
  external_secrets_namespace       = "external-secrets"
  external_secrets_service_account = "external-secrets"
  flagd_sync_secret_name           = "${var.cluster_name}/flagd-sync-token"
}

resource "aws_secretsmanager_secret" "flagd_sync_token" {
  name                    = local.flagd_sync_secret_name
  description             = "TechX TF3 flagd sync token. Secret value is intentionally managed outside Terraform state."
  recovery_window_in_days = 7

  tags = {
    Name = local.flagd_sync_secret_name
  }
}

data "aws_iam_policy_document" "external_secrets_assume_role" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [module.eks.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${module.eks.oidc_provider}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "${module.eks.oidc_provider}:sub"
      values   = ["system:serviceaccount:${local.external_secrets_namespace}:${local.external_secrets_service_account}"]
    }
  }
}

resource "aws_iam_role" "external_secrets" {
  name               = "${var.cluster_name}-external-secrets"
  assume_role_policy = data.aws_iam_policy_document.external_secrets_assume_role.json
}

resource "aws_iam_role_policy" "external_secrets_flagd_sync_token" {
  name = "${var.cluster_name}-external-secrets-flagd-sync-token"
  role = aws_iam_role.external_secrets.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadFlagdSyncToken"
        Effect = "Allow"
        Action = [
          "secretsmanager:DescribeSecret",
          "secretsmanager:GetSecretValue",
        ]
        Resource = aws_secretsmanager_secret.flagd_sync_token.arn
      },
    ]
  })
}
