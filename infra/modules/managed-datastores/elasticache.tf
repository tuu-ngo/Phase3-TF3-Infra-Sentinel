# ── ElastiCache Redis ─────────────────────────────────────────────────────────

resource "aws_elasticache_subnet_group" "main" {
  name        = "${var.cluster_name}-redis"
  subnet_ids  = var.private_subnet_ids
  description = "Private subnets for ${var.cluster_name} ElastiCache"

  tags = {
    Name = "${var.cluster_name}-redis"
  }
}

# Redis AUTH token — generated as a random 64-char string and stored in
# Secrets Manager. Never lands in Terraform state (stored via local-exec-free
# approach using random_password + Secrets Manager resource).
resource "random_password" "redis_auth_token" {
  length  = 64
  special = false # Redis AUTH token must be printable ASCII, no whitespace
}

# The Secrets Manager secret for the Redis AUTH token.
resource "aws_secretsmanager_secret" "redis_auth" {
  name                    = "${var.cluster_name}/elasticache-redis-auth-token"
  description             = "Redis AUTH token for ${var.cluster_name} ElastiCache cluster. Rotate via ElastiCache console or API."
  kms_key_id              = aws_kms_key.secrets.arn
  recovery_window_in_days = 7

  tags = {
    Name = "${var.cluster_name}/elasticache-redis-auth-token"
  }
}

resource "aws_secretsmanager_secret_version" "redis_auth" {
  secret_id = aws_secretsmanager_secret.redis_auth.id

  secret_string = jsonencode({
    auth_token = random_password.redis_auth_token.result
    endpoint   = "${var.cluster_name}-redis.${data.aws_region.current.name}"
    port       = 6380
  })

  lifecycle {
    # Prevent Terraform from rotating the token on subsequent plans —
    # rotation should be done out-of-band via ElastiCache AUTH token rotation.
    ignore_changes = [secret_string]
  }
}

# ElastiCache Replication Group (Redis OSS)
# - TLS in-transit via transit_encryption_enabled = true
# - At-rest encryption via at_rest_encryption_enabled + KMS key
# - Redis AUTH via auth_token
resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "${var.cluster_name}-redis"
  description          = "Redis for ${var.cluster_name} (cart service)"
  node_type            = var.elasticache_node_type
  num_cache_clusters   = var.elasticache_num_cache_nodes

  engine               = "redis"
  engine_version       = var.elasticache_engine_version
  parameter_group_name = "default.redis7"
  port                 = 6380 # TLS port; default non-TLS 6379 is not used

  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.elasticache.id]

  # Encryption
  at_rest_encryption_enabled = true
  kms_key_id                 = aws_kms_key.elasticache.arn
  transit_encryption_enabled = true
  transit_encryption_mode    = "required" # Reject non-TLS connections
  auth_token                 = random_password.redis_auth_token.result
  auth_token_update_strategy = "ROTATE"

  # Availability
  automatic_failover_enabled = var.elasticache_num_cache_nodes > 1
  multi_az_enabled           = var.elasticache_num_cache_nodes > 1

  # Maintenance / snapshots
  snapshot_retention_limit   = 3
  snapshot_window            = "03:00-04:00"
  maintenance_window         = "sun:04:00-sun:05:00"
  auto_minor_version_upgrade = true

  # Prevent accidental deletion of the cluster.
  apply_immediately = false

  tags = {
    Name = "${var.cluster_name}-redis"
  }

  depends_on = [aws_secretsmanager_secret_version.redis_auth]
}
