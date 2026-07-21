# Datastores module — locals + data chung.
# Tài nguyên tách theo file: kms.tf, security-groups.tf, rds.tf, elasticache.tf, msk.tf, secrets.tf.

locals {
  create = var.enabled

  # 3 store đều gate qua một cờ enabled duy nhất — apply/destroy cả tầng cùng lúc.
  count_flag = var.enabled ? 1 : 0

  common_tags = merge(var.tags, {
    Mandate   = "mandate-08-managed-migration"
    ManagedBy = "terraform"
  })

  # Ingress cho phép: SG client (node/cluster EKS) + tùy chọn bastion (RDS/ElastiCache).
  db_client_sgs = var.allowed_client_security_group_ids
  db_ops_sgs    = concat(var.allowed_client_security_group_ids, [var.bastion_security_group_id])
}
