# GitHub OIDC bootstrap

Root này giữ ownership riêng cho IAM roles được GitHub Actions dùng để plan/apply production.
State riêng nằm tại key `bootstrap/github-oidc/terraform.tfstate`, không thuộc production EKS
state.

Trong giai đoạn migration, trust policy khóa plan role vào nhánh
`deploy/account-migration-gitops`; apply chỉ được gọi thủ công từ workflow trên chính nhánh này.
`AdministratorAccess` được giữ tạm cho apply role; thu hẹp thành policy Terraform riêng là việc
phải hoàn thành trước khi khôi phục pipeline trên `main`.
