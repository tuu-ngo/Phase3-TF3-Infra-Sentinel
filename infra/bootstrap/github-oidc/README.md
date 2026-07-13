# GitHub OIDC bootstrap

Root này giữ ownership riêng cho IAM roles được GitHub Actions dùng để plan/apply production.
Nó không thuộc production EKS state và không được workflow production tự động chạy.

Không chạy `terraform apply` trước khi có phê duyệt riêng, backend riêng cho bootstrap và một
security review cho quyền của apply role. `AdministratorAccess` được giữ nguyên từ cấu hình cũ
để đợt refactor này không đồng thời thay đổi policy; thu hẹp quyền là một thay đổi độc lập.
