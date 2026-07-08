variable "region" {
  description = "AWS region - kept aligned with the ECR repo (ap-southeast-1) to avoid cross-region data transfer cost."
  type        = string
  default     = "ap-southeast-1"
}

variable "cluster_name" {
  description = "EKS cluster name"
  type        = string
  default     = "techx-corp-tf3"
}

variable "cluster_version" {
  description = "Kubernetes version for the EKS control plane"
  type        = string
  default     = "1.31"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "azs" {
  description = "Availability zones to spread subnets/nodes across"
  type        = list(string)
  default     = ["ap-southeast-1a", "ap-southeast-1b", "ap-southeast-1c"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets (EKS nodes) - one per AZ"
  type        = list(string)
  default     = ["10.0.0.0/20", "10.0.16.0/20", "10.0.32.0/20"]
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets (NAT, future NLB) - one per AZ"
  type        = list(string)
  default     = ["10.0.48.0/24", "10.0.49.0/24", "10.0.50.0/24"]
}

variable "allowed_admin_cidrs" {
  description = <<-EOT
    DEPRECATED as of 09/07 - the EKS API is private-only now (see bastion.tf).
    No longer referenced by eks.tf; kept only so old tfvars entries don't
    error on `terraform plan`. Safe to delete from terraform.tfvars.
  EOT
  type        = list(string)
  default     = []
}

variable "node_instance_type" {
  description = "Instance type for the managed node group"
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
  description = "IAM user/role ARNs (TF3 members) that should get EKS cluster-admin access entries"
  type        = list(string)
  default     = []
}
