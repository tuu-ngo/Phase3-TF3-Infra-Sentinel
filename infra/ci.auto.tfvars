# Committed (not gitignored, unlike terraform.tfvars) so CI and every team
# member's local `terraform plan` use the same values - no more drift from
# people running apply with their own incomplete local tfvars.
# ARNs here are not secret (account ID + IAM username, already visible in
# CloudTrail/console to anyone with access to this AWS account).

eks_admin_principal_arns = [
  "arn:aws:iam::012619468490:user/arthur",
  "arn:aws:iam::012619468490:user/CDO01",
  "arn:aws:iam::012619468490:user/CDO02",
  "arn:aws:iam::012619468490:user/AIO02",
]
