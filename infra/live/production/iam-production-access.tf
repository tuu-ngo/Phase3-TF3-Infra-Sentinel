data "aws_caller_identity" "production_access" {}

locals {
  production_operator_users = toset([
    "cdo01-pm",
    "cdo01-tl",
    "cdo02-pm",
    "cdo02-tl",
  ])
  production_readonly_user = "tf3-members-readonly"
  operator_user_arns = [
    for username in local.production_operator_users :
    "arn:aws:iam::${data.aws_caller_identity.production_access.account_id}:user/${username}"
  ]
  readonly_user_arn = "arn:aws:iam::${data.aws_caller_identity.production_access.account_id}:user/${local.production_readonly_user}"
}

resource "aws_iam_role" "tf3_production_operator" {
  name = "tf3-production-operator"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { AWS = "arn:aws:iam::${data.aws_caller_identity.production_access.account_id}:root" }
      Condition = {
        ArnEquals = {
          "aws:PrincipalArn" = local.operator_user_arns
        }
      }
    }]
  })
}

resource "aws_iam_role" "tf3_production_readonly" {
  name = "tf3-production-readonly"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { AWS = "arn:aws:iam::${data.aws_caller_identity.production_access.account_id}:root" }
      Condition = {
        ArnEquals = {
          "aws:PrincipalArn" = local.readonly_user_arn
        }
      }
    }]
  })
}

resource "aws_iam_policy" "assume_tf3_production_operator" {
  name = "tf3-assume-production-operator"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "sts:AssumeRole"
      Resource = aws_iam_role.tf3_production_operator.arn
    }]
  })
}

resource "aws_iam_policy" "assume_tf3_production_readonly" {
  name = "tf3-assume-production-readonly"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "sts:AssumeRole"
      Resource = aws_iam_role.tf3_production_readonly.arn
    }]
  })
}

resource "aws_iam_user_policy_attachment" "production_operator_assume_role" {
  for_each   = local.production_operator_users
  user       = each.value
  policy_arn = aws_iam_policy.assume_tf3_production_operator.arn
}

resource "aws_iam_user_policy_attachment" "production_operator_change_password" {
  for_each   = local.production_operator_users
  user       = each.value
  policy_arn = "arn:aws:iam::aws:policy/IAMUserChangePassword"
}

resource "aws_iam_user_policy_attachment" "production_readonly_assume_role" {
  user       = local.production_readonly_user
  policy_arn = aws_iam_policy.assume_tf3_production_readonly.arn
}
