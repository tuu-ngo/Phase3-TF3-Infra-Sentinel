data "aws_caller_identity" "current" {}

data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

resource "aws_iam_role" "terraform_plan" {
  name = "${var.cluster_name}-gha-terraform-plan"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = data.aws_iam_openid_connect_provider.github.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = var.terraform_plan_subjects
        }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "terraform_plan_readonly" {
  role       = aws_iam_role.terraform_plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

resource "aws_iam_role_policy" "terraform_plan_state_access" {
  name = "state-lock-and-read"
  role = aws_iam_role.terraform_plan.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = "arn:aws:s3:::${var.state_bucket_name}"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "arn:aws:s3:::${var.state_bucket_name}/${var.state_key}"
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:DescribeTable", "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem"]
        Resource = "arn:aws:dynamodb:${var.region}:${data.aws_caller_identity.current.account_id}:table/${var.lock_table_name}"
      },
    ]
  })
}

resource "aws_iam_role" "terraform_apply" {
  name = "${var.cluster_name}-gha-terraform-apply"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = data.aws_iam_openid_connect_provider.github.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = var.terraform_apply_subject
        }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "terraform_apply_admin" {
  role       = aws_iam_role.terraform_apply.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}

data "aws_iam_role" "github_actions_ecr_push" {
  name = "github-actions-ecr-push"
}

resource "aws_iam_role_policy" "github_actions_ecr_trivy_pull" {
  name = "ECRTrivyPull"
  role = data.aws_iam_role.github_actions_ecr_push.name

  policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Sid    = "AllowTrivyToPullImageLayers"
        Effect = "Allow"

        Action = [
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
        ]

        Resource = "arn:aws:ecr:${var.region}:${data.aws_caller_identity.current.account_id}:repository/techx-corp"
      },
    ]
  })
}
