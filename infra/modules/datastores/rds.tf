# RDS PostgreSQL 17.6, Multi-AZ, gp3, TLS bắt buộc, private, encryption at rest.
# Master password do RDS quản lý trong Secrets Manager (manage_master_user_password) →
# KHÔNG bao giờ nằm trong TF state. ESO đọc secret managed đó (policy ở secrets.tf).

resource "aws_db_subnet_group" "postgres" {
  count = local.count_flag

  name       = "${var.name_prefix}-postgres"
  subnet_ids = var.private_subnet_ids

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-postgres" })
}

# Parameter group: bắt buộc TLS (rds.force_ssl=1) → client không TLS bị từ chối ở tầng DB.
resource "aws_db_parameter_group" "postgres" {
  count = local.count_flag

  name   = "${var.name_prefix}-postgres17"
  family = "postgres17"

  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }

  tags = local.common_tags

  lifecycle { create_before_destroy = true }
}

resource "aws_db_instance" "postgres" {
  count = local.count_flag

  identifier     = "${var.name_prefix}-postgres"
  engine         = "postgres"
  engine_version = var.rds_engine_version
  instance_class = var.rds_instance_class

  allocated_storage     = var.rds_allocated_storage
  max_allocated_storage = var.rds_allocated_storage * 2 # autoscale storage trần gấp đôi
  storage_type          = "gp3"
  storage_encrypted     = true # encryption at rest (AWS-managed key, $0)

  db_name  = var.rds_database_name
  username = var.rds_master_username
  # Master password: RDS tạo + xoay trong Secrets Manager, không qua TF state.
  manage_master_user_password = true

  multi_az               = var.rds_multi_az
  db_subnet_group_name   = aws_db_subnet_group.postgres[0].name
  vpc_security_group_ids = [aws_security_group.rds[0].id]
  parameter_group_name   = aws_db_parameter_group.postgres[0].name
  publicly_accessible    = false # endpoint private — yêu cầu #3 directive

  backup_retention_period   = 7
  deletion_protection       = true  # chống xoá nhầm production DB
  skip_final_snapshot       = false # luôn chụp snapshot cuối khi destroy
  final_snapshot_identifier = "${var.name_prefix}-postgres-final"
  apply_immediately         = true

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-postgres" })
}
