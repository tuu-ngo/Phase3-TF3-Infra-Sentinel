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

# `gitlab-ci-deployer` là IAM user admin, chưa MFA, còn access key dài hạn, và
# KHÔNG do Terraform quản lý. Không xoá được vì pipeline GitLab đang dùng. Nên
# áp cùng boundary: nó vẫn deploy được như cũ nhưng mất đường tắt tắt audit.
# Boundary được attach thủ công (xem execution plan §9.7) vì user nằm ngoài
# state; liệt kê ở đây để statement DenyRemovingOwnBoundary chặn nó tự gỡ.
variable "additional_bounded_principal_arns" {
  description = "IAM user/role ngoài Terraform state cũng mang boundary này và không được tự gỡ."
  type        = list(string)
  default = [
    "arn:aws:iam::197826770971:user/gitlab-ci-deployer",
  ]

  validation {
    condition = alltrue([
      for arn in var.additional_bounded_principal_arns :
      can(regex("^arn:aws:iam::[0-9]{12}:(user|role)/.+$", arn))
    ])
    error_message = "Each value must be an IAM user or role ARN."
  }
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
