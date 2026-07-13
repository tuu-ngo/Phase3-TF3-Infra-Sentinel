variable "cluster_name" {
  type = string
}

variable "frontend_alb_dns_name" {
  type = string
}

variable "vpc_id" {
  description = "VPC that contains the private frontend ALB."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs available to the CloudFront VPC origin."
  type        = list(string)
}

variable "private_alb_name" {
  description = "Stable AWS Load Balancer Controller name for the private frontend ALB."
  type        = string
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
