# Security group riêng cho từng store. Nguyên tắc: inbound CHỈ từ SG được chỉ định
# (không CIDR mở), egress đóng (managed service không cần gọi ra ngoài trên các cổng này).
# RDS/ElastiCache thêm bastion SG (đường vận hành qua SSM tunnel). MSK không mở bastion.

# ---------- RDS ----------
resource "aws_security_group" "rds" {
  count = local.count_flag

  name        = "${var.name_prefix}-rds"
  description = "RDS PostgreSQL — inbound 5432 chỉ từ node/cluster SG + bastion"
  vpc_id      = var.vpc_id

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-rds" })

  lifecycle { create_before_destroy = true }
}

resource "aws_security_group_rule" "rds_ingress" {
  for_each = local.create ? toset(local.db_ops_sgs) : []

  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.rds[0].id
  source_security_group_id = each.value
  description              = "PostgreSQL 5432 from ${each.value}"
}

# ---------- ElastiCache ----------
resource "aws_security_group" "elasticache" {
  count = local.count_flag

  name        = "${var.name_prefix}-elasticache"
  description = "ElastiCache Valkey — inbound 6379 chỉ từ node/cluster SG + bastion"
  vpc_id      = var.vpc_id

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-elasticache" })

  lifecycle { create_before_destroy = true }
}

resource "aws_security_group_rule" "elasticache_ingress" {
  for_each = local.create ? toset(local.db_ops_sgs) : []

  type                     = "ingress"
  from_port                = 6379
  to_port                  = 6379
  protocol                 = "tcp"
  security_group_id        = aws_security_group.elasticache[0].id
  source_security_group_id = each.value
  description              = "Valkey 6379 from ${each.value}"
}

# ---------- MSK ----------
# Mở cổng SASL/SCRAM (9096) + TLS (9094) + SASL_SSL interbroker. Chỉ từ SG client (pod).
resource "aws_security_group" "msk" {
  count = local.count_flag

  name        = "${var.name_prefix}-msk"
  description = "MSK Kafka — inbound 9092/9094/9096 chỉ từ node/cluster SG"
  vpc_id      = var.vpc_id

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-msk" })

  lifecycle { create_before_destroy = true }
}

resource "aws_security_group_rule" "msk_ingress" {
  # Tích 2 chiều: mỗi client SG × mỗi cổng broker.
  for_each = local.create ? {
    for pair in setproduct(local.db_client_sgs, [9092, 9094, 9096]) :
    "${pair[0]}-${pair[1]}" => { sg = pair[0], port = pair[1] }
  } : {}

  type                     = "ingress"
  from_port                = each.value.port
  to_port                  = each.value.port
  protocol                 = "tcp"
  security_group_id        = aws_security_group.msk[0].id
  source_security_group_id = each.value.sg
  description              = "MSK ${each.value.port} from ${each.value.sg}"
}
