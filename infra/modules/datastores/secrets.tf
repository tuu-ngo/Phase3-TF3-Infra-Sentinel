# Credential cho 3 store trong Secrets Manager + policy cho External Secrets Operator (ESO) đọc.
#
# - RDS: dùng secret master DO RDS TỰ QUẢN (manage_master_user_password) — không nằm trong TF state.
#   ESO đọc secret đó; host/port/dbname (không nhạy cảm) đưa qua output → gitops render 3 format conn string.
# - ElastiCache AUTH token + MSK SCRAM password: sinh trong module (random_password) → vào TF state
#   (S3 mã hoá, hạn chế truy cập). Xoay sau cutover theo ADR §3 (break-glass principle).
# - MSK SCRAM secret BẮT BUỘC: tên prefix `AmazonMSK_` + mã hoá bằng CMK (không dùng key mặc định).

# ---------- ElastiCache AUTH token ----------
resource "aws_secretsmanager_secret" "elasticache_auth" {
  count = local.count_flag

  name                    = "${var.name_prefix}/elasticache-auth"
  description             = "ElastiCache Valkey AUTH token (cart store). Rotate sau cutover."
  recovery_window_in_days = 7

  tags = merge(local.common_tags, { Name = "${var.name_prefix}/elasticache-auth" })
}

resource "aws_secretsmanager_secret_version" "elasticache_auth" {
  count = local.count_flag

  secret_id = aws_secretsmanager_secret.elasticache_auth[0].id
  secret_string = jsonencode({
    auth_token = random_password.elasticache_auth[0].result
    host       = aws_elasticache_replication_group.valkey[0].primary_endpoint_address
    port       = 6379
  })
}

# ---------- MSK SASL/SCRAM ----------
resource "random_password" "msk_scram" {
  count = local.count_flag

  length  = 32
  special = false
}

resource "aws_secretsmanager_secret" "msk_scram" {
  count = local.count_flag

  # BẮT BUỘC prefix AmazonMSK_ để associate được với cluster.
  name                    = "AmazonMSK_${var.name_prefix}/kafka-scram"
  description             = "MSK SASL/SCRAM credential (checkout/accounting/fraud-detection). Rotate sau cutover."
  kms_key_id              = aws_kms_key.datastores[0].arn # CMK bắt buộc cho MSK
  recovery_window_in_days = 7

  tags = merge(local.common_tags, { Name = "AmazonMSK_${var.name_prefix}/kafka-scram" })
}

resource "aws_secretsmanager_secret_version" "msk_scram" {
  count = local.count_flag

  secret_id = aws_secretsmanager_secret.msk_scram[0].id
  # MSK SCRAM yêu cầu đúng field username/password.
  secret_string = jsonencode({
    username = "techx"
    password = random_password.msk_scram[0].result
  })
}

# Gắn SCRAM secret vào MSK cluster (MSK đọc thẳng từ Secrets Manager).
resource "aws_msk_scram_secret_association" "kafka" {
  count = local.count_flag

  cluster_arn     = aws_msk_cluster.kafka[0].arn
  secret_arn_list = [aws_secretsmanager_secret.msk_scram[0].arn]

  depends_on = [aws_secretsmanager_secret_version.msk_scram]
}

# ---------- Policy cho ESO đọc 3 secret ----------
# Theo pattern eks-platform: policy scoped đúng ARN cần, gắn vào role ESO sẵn có.
data "aws_iam_policy_document" "external_secrets_datastores" {
  count = local.count_flag

  statement {
    sid    = "ReadDatastoreSecrets"
    effect = "Allow"
    actions = [
      "secretsmanager:DescribeSecret",
      "secretsmanager:GetSecretValue",
    ]
    resources = [
      aws_db_instance.postgres[0].master_user_secret[0].secret_arn,
      aws_secretsmanager_secret.elasticache_auth[0].arn,
      aws_secretsmanager_secret.msk_scram[0].arn,
    ]
  }

  # Decrypt: CMK cho MSK SCRAM secret; key RDS-managed cho secret master RDS.
  statement {
    sid     = "DecryptDatastoreSecrets"
    effect  = "Allow"
    actions = ["kms:Decrypt"]
    resources = [
      aws_kms_key.datastores[0].arn,
      aws_db_instance.postgres[0].master_user_secret[0].kms_key_id,
    ]
  }
}

resource "aws_iam_role_policy" "external_secrets_datastores" {
  count = local.count_flag

  name   = "${var.cluster_name}-external-secrets-datastores"
  role   = var.external_secrets_role_name
  policy = data.aws_iam_policy_document.external_secrets_datastores[0].json
}
