# Đề xuất RBAC Least-Privilege và quy trình Break-Glass

## 1. Bối cảnh
Hiện tại, các tài khoản IAM cá nhân như `arthur`, `CDO01`, `CDO02`, `AIO02` và `mentor` đều được gán `AdministratorAccess` trên AWS account, bao gồm cả quyền truy cập Kubernetes cluster thông qua `eks_admin_principal_arns`. Điều này tạo ra rủi ro bảo mật nghiêm trọng do thiếu nguyên tắc least-privilege và khả năng theo dõi thay đổi thủ công ngoài luồng GitOps.

Sự cố NetworkPolicy áp tay gần đây (INC-20260716-CHECKOUT-OUTAGE) là một ví dụ điển hình về hậu quả của lỗ hổng này, khi các thay đổi trực tiếp vào cluster không qua GitOps dẫn đến gián đoạn dịch vụ.

## 2. Mục tiêu
*   Thực thi nguyên tắc least-privilege cho quyền truy cập cluster.
*   Tách biệt rõ ràng quyền thao tác thông qua GitOps và quyền can thiệp khẩn cấp (break-glass).
*   Đảm bảo khả năng xử lý sự cố khẩn cấp vẫn duy trì, nhưng có kiểm soát và audit trail rõ ràng.

## 3. Đề xuất RBAC Least-Privilege
Để siết chặt quyền, chúng tôi đề xuất phân tách các vai trò như sau:

### 3.1. Vai trò GitOps (Default)
*   **Mục đích**: Dành cho các hoạt động vận hành và phát triển hàng ngày, mọi thay đổi đều phải đi qua quy trình GitOps (Pull Request, review, merge vào `main`, ArgoCD tự động đồng bộ).
*   **Quyền hạn**: Tài khoản IAM của người dùng sẽ không có quyền `kubectl apply/create/patch/delete` trực tiếp vào cluster. Thay vào đó, các quyền này sẽ được gán cho Service Account của ArgoCD (`argocd-application-controller`).
*   **Cơ chế**: Người dùng sẽ tương tác với Git (commit, PR) và ArgoCD sẽ là thực thể duy nhất có quyền sửa đổi tài nguyên trên cluster theo định nghĩa trong Git.

### 3.2. Vai trò Break-Glass (Khẩn cấp)
*   **Mục đích**: Dành riêng cho các tình huống khẩn cấp nghiêm trọng (ví dụ: cluster sập, ArgoCD không hoạt động, cần vá nóng để khôi phục dịch vụ ngay lập tức).
*   **Quyền hạn**: Một tập hợp rất hạn chế các tài khoản IAM (ví dụ: chỉ 1-2 tài khoản được ủy quyền cao nhất) sẽ giữ lại quyền `kubectl apply/create/patch/delete` trực tiếp, tương đương với `AdministratorAccess` hiện tại hoặc các quyền cần thiết cho containment.
*   **Cơ chế**: 
    *   **Truy cập có kiểm soát**: Các tài khoản này sẽ được bảo vệ bằng MFA mạnh mẽ (ví dụ: hardware MFA).
    *   **Audit Trail**: Mọi hành động thực hiện bằng tài khoản break-glass phải được ghi log đầy đủ (ví dụ: thông qua AWS CloudTrail tích hợp với EKS Audit Logs) và có cảnh báo (ví dụ: gửi thông báo đến kênh Slack/PagerDuty).
    *   **Quy trình rõ ràng**: Bắt buộc phải có một quy trình 