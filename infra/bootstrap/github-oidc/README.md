# GitHub OIDC bootstrap

Root này giữ ownership riêng cho IAM roles được GitHub Actions dùng để plan/apply production.
State riêng nằm tại key `bootstrap/github-oidc/terraform.tfstate`, không thuộc production EKS
state.

Sau migration, plan role chỉ trust protected `main` và pull-request subject; deploy branch cũ
không còn quyền assume role. Apply chỉ được gọi thủ công từ workflow trên `main` thông qua
GitHub Environment `production`. Apply role vẫn còn `AdministratorAccess`; thu hẹp thành policy
Terraform riêng là hardening còn mở và phải được xử lý bằng một plan IAM độc lập.
