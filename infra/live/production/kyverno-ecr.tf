data "aws_caller_identity" "kyverno_ecr" {}

data "aws_partition" "kyverno_ecr" {}

data "aws_iam_openid_connect_provider" "kyverno_ecr" {
  arn = module.eks_platform.oidc_provider_arn
}

data "aws_iam_policy_document" "kyverno_ecr_assume_role" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [module.eks_platform.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${replace(data.aws_iam_openid_connect_provider.kyverno_ecr.url, "https://", "")}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "${replace(data.aws_iam_openid_connect_provider.kyverno_ecr.url, "https://", "")}:sub"
      values = [
        "system:serviceaccount:kyverno:kyverno-admission-controller",
        "system:serviceaccount:kyverno:kyverno-background-controller",
        "system:serviceaccount:kyverno:kyverno-cleanup-controller",
        "system:serviceaccount:kyverno:kyverno-reports-controller",
      ]
    }
  }
}

resource "aws_iam_role" "kyverno_ecr" {
  name               = "${var.cluster_name}-kyverno-ecr"
  assume_role_policy = data.aws_iam_policy_document.kyverno_ecr_assume_role.json
}

resource "aws_iam_role_policy" "kyverno_ecr_read" {
  name = "${var.cluster_name}-kyverno-ecr-read"
  role = aws_iam_role.kyverno_ecr.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "GetEcrAuthorizationToken"
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Sid    = "ReadTechxCorpImages"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:BatchGetImage",
          "ecr:DescribeImages",
          "ecr:DescribeRepositories",
          "ecr:GetDownloadUrlForLayer",
        ]
        Resource = "arn:${data.aws_partition.kyverno_ecr.partition}:ecr:${var.region}:${data.aws_caller_identity.kyverno_ecr.account_id}:repository/techx-corp"
      },
    ]
  })
}
