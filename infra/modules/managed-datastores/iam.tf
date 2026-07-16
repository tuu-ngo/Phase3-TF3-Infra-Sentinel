# ── IAM policy for EKS workloads reading datastore secrets ───────────────────
#
# This policy is NOT attached to any role here — it is exported as an ARN so
# that the eks-platform module (or application-specific IRSA roles) can attach
# it to the relevant service account roles.
#
# Grants:
#   - secretsmanager:GetSecretValue / DescribeSecret on all datastore secrets
#   - kms:Decrypt / GenerateDataKey on the secrets KMS key
#
# Scope: deliberately restrictive — only the three secrets this module owns.

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_partition" "current" {}

resource "aws_iam_policy" "datastore_secrets_read" {
  name        = "${var.cluster_name}-datastore-secrets-read"
  description = "Read datastore credentials from Secrets Manager for ${var.cluster_name}"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadDatastoreSecrets"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret",
        ]
        Resource = [
          # RDS master user secret (managed by RDS itself — ARN resolved at runtime)
          "arn:${data.aws_partition.current.partition}:secretsmanager:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:secret:${var.cluster_name}/rds/*",
          aws_secretsmanager_secret.redis_auth.arn,
          aws_secretsmanager_secret.msk_scram.arn,
        ]
      },
      {
        Sid    = "DecryptSecretsKMS"
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey",
          "kms:DescribeKey",
        ]
        Resource = [
          aws_kms_key.secrets.arn,
        ]
      },
    ]
  })
}

# ── MSK IAM auth policy ───────────────────────────────────────────────────────
# Allows IRSA-enabled pods to connect to MSK via IAM authentication (port 9098).
# Scoped to the specific cluster ARN.

resource "aws_iam_policy" "msk_iam_auth" {
  name        = "${var.cluster_name}-msk-iam-auth"
  description = "MSK IAM authentication for EKS pods in ${var.cluster_name}"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "MSKClusterConnect"
        Effect = "Allow"
        Action = [
          "kafka-cluster:Connect",
          "kafka-cluster:AlterCluster",
          "kafka-cluster:DescribeCluster",
        ]
        Resource = aws_msk_cluster.main.arn
      },
      {
        Sid    = "MSKTopicAccess"
        Effect = "Allow"
        Action = [
          "kafka-cluster:*Topic*",
          "kafka-cluster:WriteData",
          "kafka-cluster:ReadData",
        ]
        Resource = "arn:${data.aws_partition.current.partition}:kafka:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:topic/${var.cluster_name}-kafka/*"
      },
      {
        Sid    = "MSKGroupAccess"
        Effect = "Allow"
        Action = [
          "kafka-cluster:AlterGroup",
          "kafka-cluster:DescribeGroup",
        ]
        Resource = "arn:${data.aws_partition.current.partition}:kafka:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:group/${var.cluster_name}-kafka/*"
      },
    ]
  })
}
