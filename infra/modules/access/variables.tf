variable "region" {
  type = string
}

variable "cluster_name" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "vpc_cidr" {
  description = "VPC CIDR used to restrict bastion HTTPS egress to private AWS endpoints and the EKS API."
  type        = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "cluster_security_group_id" {
  type = string
}

variable "cluster_endpoint" {
  type = string
}
