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
  description = "Controlled edge migration phase: public, waf, staging, or private."
  type        = string
  default     = "public"

  validation {
    condition     = contains(["public", "waf", "staging", "private"], var.edge_phase)
    error_message = "edge_phase must be one of: public, waf, staging, private."
  }
}

variable "cloudfront_staging_selector" {
  description = "Sensitive selector value for header-routed CloudFront staging requests."
  type        = string
  default     = ""
  sensitive   = true
}
