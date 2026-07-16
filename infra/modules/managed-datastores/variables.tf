variable "cluster_name" {
  description = "EKS cluster name — used as prefix for all resource names."
  type        = string
}

variable "vpc_id" {
  description = "VPC ID where all managed datastore resources will be created."
  type        = string
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs for subnet groups (RDS, ElastiCache, MSK)."
  type        = list(string)
}

variable "vpc_cidr" {
  description = "VPC CIDR block — used for inbound SG rules from EKS nodes."
  type        = string
}

variable "eks_node_security_group_id" {
  description = "EKS node security group ID — granted ingress to all managed datastores."
  type        = string
}

# ── RDS ──────────────────────────────────────────────────────────────────────

variable "rds_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.micro"

  validation {
    condition     = can(regex("^db\\.t4g\\.(micro|small)$", var.rds_instance_class))
    error_message = "rds_instance_class must be db.t4g.micro or db.t4g.small."
  }
}

variable "rds_db_name" {
  description = "Initial database name created when the RDS instance is provisioned."
  type        = string
  default     = "techxdb"
}

variable "rds_engine_version" {
  description = "PostgreSQL engine version."
  type        = string
  default     = "16.3"
}

variable "rds_allocated_storage" {
  description = "Allocated storage in GiB for the RDS instance."
  type        = number
  default     = 20
}

variable "rds_multi_az" {
  description = "Enable Multi-AZ deployment for RDS. Recommended for production."
  type        = bool
  default     = true
}

variable "rds_deletion_protection" {
  description = "Prevent accidental deletion of the RDS instance."
  type        = bool
  default     = true
}

variable "rds_backup_retention_days" {
  description = "Number of days to retain automated backups."
  type        = number
  default     = 7
}

# ── ElastiCache ──────────────────────────────────────────────────────────────

variable "elasticache_node_type" {
  description = "ElastiCache node type."
  type        = string
  default     = "cache.t4g.micro"
}

variable "elasticache_engine_version" {
  description = "Redis engine version."
  type        = string
  default     = "7.1"
}

variable "elasticache_num_cache_nodes" {
  description = "Number of cache nodes (1 = single-node, no replication)."
  type        = number
  default     = 1
}

# ── MSK ──────────────────────────────────────────────────────────────────────

variable "msk_instance_type" {
  description = "MSK broker instance type."
  type        = string
  default     = "kafka.t3.small"
}

variable "msk_kafka_version" {
  description = "Apache Kafka version for MSK."
  type        = string
  default     = "3.6.0"
}

variable "msk_number_of_broker_nodes" {
  description = "Number of MSK broker nodes. Must be a multiple of the number of AZs used."
  type        = number
  default     = 3
}

variable "msk_broker_storage_gib" {
  description = "EBS storage per MSK broker in GiB."
  type        = number
  default     = 20
}
