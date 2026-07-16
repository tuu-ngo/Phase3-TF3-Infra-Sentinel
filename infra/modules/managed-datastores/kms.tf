# ── KMS keys — one per service for independent key rotation & access control ──

resource "aws_kms_key" "rds" {
  description             = "RDS at-rest encryption — ${var.cluster_name}"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = {
    Name = "${var.cluster_name}-rds"
  }
}

resource "aws_kms_alias" "rds" {
  name          = "alias/${var.cluster_name}-rds"
  target_key_id = aws_kms_key.rds.key_id
}

resource "aws_kms_key" "elasticache" {
  description             = "ElastiCache at-rest encryption — ${var.cluster_name}"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = {
    Name = "${var.cluster_name}-elasticache"
  }
}

resource "aws_kms_alias" "elasticache" {
  name          = "alias/${var.cluster_name}-elasticache"
  target_key_id = aws_kms_key.elasticache.key_id
}

resource "aws_kms_key" "msk" {
  description             = "MSK at-rest encryption — ${var.cluster_name}"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = {
    Name = "${var.cluster_name}-msk"
  }
}

resource "aws_kms_alias" "msk" {
  name          = "alias/${var.cluster_name}-msk"
  target_key_id = aws_kms_key.msk.key_id
}

resource "aws_kms_key" "secrets" {
  description             = "Secrets Manager encryption for managed datastore credentials — ${var.cluster_name}"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = {
    Name = "${var.cluster_name}-datastore-secrets"
  }
}

resource "aws_kms_alias" "secrets" {
  name          = "alias/${var.cluster_name}-datastore-secrets"
  target_key_id = aws_kms_key.secrets.key_id
}
