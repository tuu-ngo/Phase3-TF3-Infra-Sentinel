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

variable "ci_audit_boundary_name" {
  description = "Tên managed policy dùng làm permissions boundary cho hai GitHub Actions Terraform role."
  type        = string
  default     = "techx-corp-tf3-ci-audit-boundary"
}

# Mặc định false: apply lần đầu chỉ TẠO policy để review, CI chạy như cũ.
# Chỉ đặt true sau khi iam:SimulatePrincipalPolicy chứng minh baseline Terraform
# vẫn allowed và các kill switch audit là explicitDeny.
# Đặt lại false là đường rollback: apply lại root này sẽ gỡ boundary.
variable "enable_ci_audit_boundary" {
  description = "Attach permissions boundary Mandate 12 vào terraform_plan/terraform_apply. Xem ci-audit-boundary.tf."
  type        = bool
  default     = false
}
