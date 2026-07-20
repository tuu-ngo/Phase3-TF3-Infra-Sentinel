# Customer-managed KMS key — BẮT BUỘC cho MSK SASL/SCRAM secret: MSK từ chối secret mã hoá
# bằng key mặc định `aws/secretsmanager`. RDS/ElastiCache at-rest dùng AWS-managed key ($0),
# nên CMK này chỉ phục vụ SCRAM secret (+ dùng luôn cho MSK at-rest vì đã có sẵn). ADR §3.

resource "aws_kms_key" "datastores" {
  count = local.count_flag

  description             = "${var.name_prefix} datastores CMK (MSK SCRAM secret + MSK at-rest)"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-datastores"
  })
}

resource "aws_kms_alias" "datastores" {
  count = local.count_flag

  name          = "alias/${var.name_prefix}-datastores"
  target_key_id = aws_kms_key.datastores[0].key_id
}
