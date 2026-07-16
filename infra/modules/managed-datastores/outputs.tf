# ── RDS ──────────────────────────────────────────────────────────────────────

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint (host:port). Use via Secrets Manager — do not embed in app config directly."
  value       = aws_db_instance.main.endpoint
}

output "rds_db_name" {
  description = "RDS database name."
  value       = aws_db_instance.main.db_name
}

output "rds_secret_arn" {
  description = "Secrets Manager ARN for the RDS master user credentials (managed by RDS)."
  value       = aws_db_instance.main.master_user_secret[0].secret_arn
}

output "rds_security_group_id" {
  description = "Security group ID attached to the RDS instance."
  value       = aws_security_group.rds.id
}

output "rds_kms_key_arn" {
  description = "KMS key ARN used for RDS at-rest encryption."
  value       = aws_kms_key.rds.arn
}

# ── ElastiCache ──────────────────────────────────────────────────────────────

output "redis_primary_endpoint" {
  description = "ElastiCache Redis primary endpoint (host:port). TLS on port 6380."
  value       = "${aws_elasticache_replication_group.redis.primary_endpoint_address}:6380"
}

output "redis_reader_endpoint" {
  description = "ElastiCache Redis reader endpoint (available when num_cache_clusters > 1)."
  value       = aws_elasticache_replication_group.redis.reader_endpoint_address
}

output "redis_auth_secret_arn" {
  description = "Secrets Manager ARN containing the Redis AUTH token."
  value       = aws_secretsmanager_secret.redis_auth.arn
}

output "redis_security_group_id" {
  description = "Security group ID attached to the ElastiCache cluster."
  value       = aws_security_group.elasticache.id
}

# ── MSK ──────────────────────────────────────────────────────────────────────

output "msk_bootstrap_brokers_tls" {
  description = "MSK TLS bootstrap broker endpoints (SASL/SCRAM on port 9094)."
  value       = aws_msk_cluster.main.bootstrap_brokers_sasl_scram
}

output "msk_bootstrap_brokers_iam" {
  description = "MSK IAM bootstrap broker endpoints (IRSA-based auth on port 9098)."
  value       = aws_msk_cluster.main.bootstrap_brokers_sasl_iam
}

output "msk_cluster_arn" {
  description = "MSK cluster ARN."
  value       = aws_msk_cluster.main.arn
}

output "msk_scram_secret_arn" {
  description = "Secrets Manager ARN for the MSK SASL/SCRAM bootstrap credential. Set the secret value before associating."
  value       = aws_secretsmanager_secret.msk_scram.arn
}

output "msk_security_group_id" {
  description = "Security group ID attached to the MSK brokers."
  value       = aws_security_group.msk.id
}

# ── IAM ──────────────────────────────────────────────────────────────────────

output "datastore_secrets_read_policy_arn" {
  description = "IAM policy ARN — attach to any IRSA role that needs to read datastore credentials."
  value       = aws_iam_policy.datastore_secrets_read.arn
}

output "msk_iam_auth_policy_arn" {
  description = "IAM policy ARN — attach to IRSA roles for MSK IAM-based Kafka authentication."
  value       = aws_iam_policy.msk_iam_auth.arn
}
