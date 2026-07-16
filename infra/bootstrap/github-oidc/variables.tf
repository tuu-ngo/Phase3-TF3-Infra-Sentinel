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

variable "terraform_plan_subjects" {
  type = set(string)
  default = [
    "repo:tuu-ngo/Phase3-TF3-Infra-Sentinel:ref:refs/heads/main",
    "repo:tuu-ngo/Phase3-TF3-Infra-Sentinel:pull_request",
  ]
}

variable "terraform_apply_subject" {
  type    = string
  default = "repo:tuu-ngo/Phase3-TF3-Infra-Sentinel:environment:production"
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
