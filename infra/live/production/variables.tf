variable "region" {
  description = "AWS region for the production platform."
  type        = string
  default     = "ap-southeast-1"
}

variable "cluster_name" {
  description = "EKS cluster name."
  type        = string
  default     = "techx-corp-tf3"
}

variable "cluster_version" {
  description = "Kubernetes version for the EKS control plane and managed node group."
  type        = string
  default     = "1.35"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "azs" {
  description = "Availability zones used by production subnets."
  type        = list(string)
  default     = ["ap-southeast-1a", "ap-southeast-1b", "ap-southeast-1c"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private EKS subnets."
  type        = list(string)
  default     = ["10.0.0.0/20", "10.0.16.0/20", "10.0.32.0/20"]
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets."
  type        = list(string)
  default     = ["10.0.48.0/24", "10.0.49.0/24", "10.0.50.0/24"]
}

variable "node_instance_type" {
  description = "Instance type for the managed node group."
  type        = string
  default     = "t3.large"
}

variable "node_desired_size" {
  type    = number
  default = 3
}

variable "node_min_size" {
  type    = number
  default = 3
}

variable "node_max_size" {
  type    = number
  default = 6
}

variable "stateful_node_availability_zone" {
  description = "Availability zone for the dedicated on-demand stateful node group."
  type        = string
  default     = "ap-southeast-1a"

  validation {
    condition     = can(regex("^ap-southeast-1[a-c]$", var.stateful_node_availability_zone))
    error_message = "stateful_node_availability_zone must be an ap-southeast-1 availability zone."
  }
}

variable "stateful_node_instance_type" {
  description = "Instance type for the dedicated on-demand stateful node group."
  type        = string
  default     = "t3.medium"
}

variable "eks_admin_principal_arns" {
  description = "IAM principal ARNs that receive EKS cluster-admin access."
  type        = list(string)
  default     = []
}

variable "frontend_alb_dns_name" {
  description = "DNS name of the Kubernetes-managed frontend-proxy ALB."
  type        = string
  default     = "k8s-techxtf3-frontend-3153771b08-956551046.ap-southeast-1.elb.amazonaws.com"
}

variable "private_alb_name" {
  description = "Stable AWS Load Balancer Controller name for the private frontend ALB."
  type        = string
  default     = "techx-tf3-frontend-internal"
}

variable "edge_phase" {
  description = "Controlled edge migration phase: public, waf, staging, private, or rollback."
  type        = string
  default     = "public"

  validation {
    condition     = contains(["public", "waf", "staging", "private", "rollback"], var.edge_phase)
    error_message = "edge_phase must be one of: public, waf, staging, private, rollback."
  }
}

variable "cloudfront_staging_selector" {
  description = "Sensitive selector value for header-routed CloudFront staging requests."
  type        = string
  default     = ""
  sensitive   = true
}

# REL-17 (docs/backlog/cdo02-reliability-cost-backlog.md) - SSO-based access to the
# private EKS API via Cloudflare Zero Trust, as an addition to (not replacement of) the
# SSM bastion. Defaults keep this entirely inert until someone deliberately opts in -
# see docs/runbooks/cloudflare-zero-trust-access.md before setting enable = true.
variable "enable_cloudflare_access" {
  description = "Provision the Cloudflare Tunnel + Access application for SSO-based EKS API access. Requires CLOUDFLARE_API_TOKEN env var and the other cloudflare_* variables set."
  type        = bool
  default     = false
}

variable "cloudflare_account_id" {
  description = "Cloudflare account ID. Required when enable_cloudflare_access = true."
  type        = string
  default     = ""
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone ID for the domain hosting the tunnel hostname. Required when enable_cloudflare_access = true."
  type        = string
  default     = ""
}

variable "cloudflare_zone_name" {
  description = "Domain name matching cloudflare_zone_id, e.g. techx-tf3-ops.com."
  type        = string
  default     = ""
}

variable "cloudflare_tunnel_hostname" {
  description = "Public hostname proxying to the EKS API, e.g. kubectl.techx-tf3-ops.com. Required when enable_cloudflare_access = true."
  type        = string
  default     = ""
}

variable "cloudflare_allowed_email_domain" {
  description = "Email domain allowed to authenticate via SSO (Access policy). Leave empty and use cloudflare_allowed_emails for a short allowlist instead."
  type        = string
  default     = ""
}

variable "cloudflare_allowed_emails" {
  description = "Explicit allowlist of emails permitted to authenticate, used when cloudflare_allowed_email_domain is empty."
  type        = list(string)
  default     = []
}

# ── Mandate 08: AWS Managed Datastores ──────────────────────────────────────

# ── RDS ──────────────────────────────────────────────────────────────────────

variable "rds_instance_class" {
  description = "RDS PostgreSQL instance class."
  type        = string
  default     = "db.t4g.micro"
}

variable "rds_db_name" {
  description = "Initial PostgreSQL database name."
  type        = string
  default     = "techxdb"
}

variable "rds_engine_version" {
  description = "RDS PostgreSQL engine version."
  type        = string
  default     = "16.3"
}

variable "rds_multi_az" {
  description = "Enable Multi-AZ for RDS. Set false only for cost reduction in non-prod."
  type        = bool
  default     = true
}

variable "rds_deletion_protection" {
  description = "Enable RDS deletion protection."
  type        = bool
  default     = true
}

# ── ElastiCache ──────────────────────────────────────────────────────────────

variable "elasticache_node_type" {
  description = "ElastiCache Redis node type."
  type        = string
  default     = "cache.t4g.micro"
}

variable "elasticache_engine_version" {
  description = "ElastiCache Redis engine version."
  type        = string
  default     = "7.1"
}

# ── MSK ──────────────────────────────────────────────────────────────────────

variable "msk_instance_type" {
  description = "MSK broker instance type."
  type        = string
  default     = "kafka.t3.small"
}

variable "msk_kafka_version" {
  description = "MSK Kafka version."
  type        = string
  default     = "3.6.0"
}

variable "msk_number_of_broker_nodes" {
  description = "Number of MSK broker nodes. Must be a multiple of the number of AZs (3)."
  type        = number
  default     = 3
}
