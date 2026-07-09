# CI/CD roles for GitHub Actions (infra/ repo, Terraform plan/apply).
#
# Why: repeated incidents (allowlist overwritten twice, CDO02 hand-editing a
# security group outside Terraform) all trace back to every team member
# running `terraform apply` from their own machine with their own local
# tfvars, no review, no single source of truth for what's about to change.
#
# Two roles, split by trust condition:
#  - plan: any ref/PR in the repo can assume it (read-only) -> used on every
#    PR to post the diff for review before merge.
#  - apply: ONLY the main branch can assume it (mirrors the existing
#    build-push-ecr.yml pattern) -> only runs after a PR is reviewed and
#    merged, gated further by the "production" GitHub Environment requiring
#    manual approval.
# No IAM user needs to run `terraform apply` locally anymore.

data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

locals {
  github_repo = "tuu-ngo/Phase3-TF3-Infra-Sentinel"
}

# --- Plan role: read-only, any branch/PR ---

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
        }
        StringLike = {
          "token.actions.githubusercontent.com:sub" = "repo:${local.github_repo}:*"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "terraform_plan_readonly" {
  role       = aws_iam_role.terraform_plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

# ReadOnlyAccess doesn't cover DynamoDB lock writes or the S3 state object -
# `terraform plan` still takes the state lock even though it doesn't modify
# infrastructure.
resource "aws_iam_role_policy" "terraform_plan_state_access" {
  name = "state-lock-and-read"
  role = aws_iam_role.terraform_plan.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
        Resource = [
          "arn:aws:s3:::techx-corp-tf3-terraform-state",
          "arn:aws:s3:::techx-corp-tf3-terraform-state/*",
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem"]
        Resource = "arn:aws:dynamodb:${var.region}:*:table/techx-corp-tf3-terraform-lock"
      },
    ]
  })
}

# --- Apply role: full write, main branch only (post-merge) ---

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
        }
        StringLike = {
          "token.actions.githubusercontent.com:sub" = "repo:${local.github_repo}:ref:refs/heads/main"
        }
      }
    }]
  })
}

# Matches what every human IAM user already has (AdministratorAccess) - not
# narrowing scope here, just moving *who* can exercise it from individuals
# to a reviewed, audited pipeline. Tightening this to a least-privilege
# policy is a separate follow-up (needs a pass with CDO01 - Security pillar).
resource "aws_iam_role_policy_attachment" "terraform_apply_admin" {
  role       = aws_iam_role.terraform_apply.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}

output "terraform_plan_role_arn" {
  value = aws_iam_role.terraform_plan.arn
}

output "terraform_apply_role_arn" {
  value = aws_iam_role.terraform_apply.arn
}
