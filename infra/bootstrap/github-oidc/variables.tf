variable "region" {
  type    = string
  default = "ap-southeast-1"
}

variable "cluster_name" {
  type    = string
  default = "techx-corp-tf3"
}

variable "github_repository" {
  type    = string
  default = "tuu-ngo/Phase3-TF3-Infra-Sentinel"
}

variable "state_bucket_name" {
  type    = string
  default = "techx-tf3-197826770971-tfstate"
}

variable "state_key" {
  type    = string
  default = "eks-baseline/terraform.tfstate"
}

variable "lock_table_name" {
  type    = string
  default = "techx-tf3-terraform-lock"
}
