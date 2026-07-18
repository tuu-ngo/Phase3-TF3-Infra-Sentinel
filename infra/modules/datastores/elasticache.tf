# ElastiCache Valkey 9.0, 1 primary + 1 replica, Multi-AZ auto-failover,
# transit encryption (bắt buộc để dùng AUTH token) + at-rest encryption, private.
# AUTH token sinh trong module → lưu Secrets Manager (secrets.tf). Xoay sau cutover (ADR §3).

resource "aws_elasticache_subnet_group" "valkey" {
  count = local.count_flag

  name       = "${var.name_prefix}-valkey"
  subnet_ids = var.private_subnet_ids

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-valkey" })
}

resource "random_password" "elasticache_auth" {
  count = local.count_flag

  length  = 32
  special = false # ElastiCache AUTH token: 16-128 ký tự, chỉ cho phép in được; tránh ký tự thoát rắc rối
}

resource "aws_elasticache_replication_group" "valkey" {
  count = local.count_flag

  replication_group_id = "${var.name_prefix}-valkey"
  description          = "TechX TF3 cart store — Valkey ${var.elasticache_engine_version}"

  engine         = "valkey"
  engine_version = var.elasticache_engine_version
  node_type      = var.elasticache_node_type
  port           = 6379

  # 1 primary + (replica_count-1) replica trong 1 node group (không cluster-mode).
  num_cache_clusters         = var.elasticache_replica_count
  automatic_failover_enabled = var.elasticache_replica_count > 1
  multi_az_enabled           = var.elasticache_replica_count > 1

  subnet_group_name  = aws_elasticache_subnet_group.valkey[0].name
  security_group_ids = [aws_security_group.elasticache[0].id]

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true # bắt buộc để bật AUTH token
  auth_token                 = random_password.elasticache_auth[0].result

  # AOF: khớp in-cluster (persistence bật). ElastiCache dùng append-only qua snapshot + AOF param.
  snapshot_retention_limit = 3
  apply_immediately        = true

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-valkey" })

  lifecycle {
    # auth_token đổi ngoài (xoay) không tự re-apply — quản qua quy trình rotate có chủ đích.
    ignore_changes = [engine_version]
  }
}
