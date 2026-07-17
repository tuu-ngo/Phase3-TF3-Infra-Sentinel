variable "cluster_name" {
  type = string
}

variable "cluster_version" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "node_instance_type" {
  type = string
}

variable "node_desired_size" {
  type = number
}

variable "node_min_size" {
  type = number
}

variable "node_max_size" {
  type = number
}

variable "stateful_node_subnet_id" {
  description = "Private subnet for the dedicated on-demand stateful node group."
  type        = string
}

variable "stateful_node_instance_type" {
  description = "Instance type for the dedicated on-demand stateful node group."
  type        = string
}

variable "eks_admin_principal_arns" {
  type = list(string)
}

variable "eks_kubernetes_group_principals" {
  description = "IAM principal ARNs mapped to Kubernetes groups without an EKS cluster access policy."
  type = map(object({
    principal_arn     = string
    kubernetes_groups = list(string)
  }))
  default = {}
}
