# Hướng dẫn truy cập — TechX Corp trên account 197826770971

Hệ thống đang LIVE trên account AWS mới (song song với account BTC đang bị hold).
Có 2 mức truy cập: **(A) xem storefront** (ai cũng vào được) và **(B) kubectl/ops UI**
(cần AWS creds + được cấp quyền cluster).

| Thông tin | Giá trị |
|---|---|
| Account | `197826770971` |
| Region | `ap-southeast-1` |
| Cluster | `techx-corp-tf3` |
| Namespace app | `techx-tf3` |
| Bastion (SSM) | `i-02a8d3e39b87180ce` |
| EKS endpoint host | `ADA05FFC84146C0AED730F78786EB320.gr7.ap-southeast-1.eks.amazonaws.com` |

---

## A. Xem storefront (không cần gì)

🔒 **HTTPS (chính):** https://d2tn71186d7ilz.cloudfront.net

Mở trình duyệt là thấy. Đây là mặt tiền công khai — chia sẻ thoải mái.

---

## B. Truy cập cluster (kubectl) + ops UI

> EKS API là **private-only** — không vào thẳng được, phải đi qua **SSM bastion** (không cần IP
> tĩnh, không cần SSH key; xác thực bằng IAM).

### B0. Điều kiện tiên quyết (làm 1 lần)
1. **AWS creds account 197826770971**: tạo Access Key trên IAM Console → `aws configure --profile techx-new`
   (region `ap-southeast-1`). Kiểm tra: `aws sts get-caller-identity --profile techx-new`.
2. **Được cấp quyền cluster**: ARN IAM của bạn phải nằm trong EKS access entry. Nếu chạy bước B2
   mà lỗi `Unauthorized`/`You must be logged in`, gửi ARN của bạn (`aws sts get-caller-identity`)
   cho CDO02 để thêm vào `infra/ci.auto.tfvars` (`eks_admin_principal_arns`) + `terraform apply`.
3. **session-manager-plugin** cài sẵn (cho lệnh `aws ssm start-session`):
   https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html

### B1. Mở tunnel (giữ terminal này chạy)
```
set AWS_PROFILE=techx-new
aws ssm start-session --target i-02a8d3e39b87180ce --document-name AWS-StartPortForwardingSessionToRemoteHost --parameters host="ADA05FFC84146C0AED730F78786EB320.gr7.ap-southeast-1.eks.amazonaws.com",portNumber="443",localPortNumber="8443" --region ap-southeast-1
```
> Windows PowerShell: `$env:AWS_PROFILE="techx-new"` thay cho `set`. Mac/Linux: `export AWS_PROFILE=techx-new`.
> Chờ thấy dòng `Waiting for connections...` là tunnel mở (giữ nguyên terminal này).

### B2. Trỏ kubectl vào tunnel (terminal KHÁC)
```
set AWS_PROFILE=techx-new
aws eks update-kubeconfig --name techx-corp-tf3 --region ap-southeast-1
kubectl config set-cluster arn:aws:eks:ap-southeast-1:197826770971:cluster/techx-corp-tf3 --server=https://localhost:8443 --insecure-skip-tls-verify=true
kubectl -n techx-tf3 get pods
```
Thấy danh sách pod `Running` = vào được.

### B3. Ops UI (Grafana / Jaeger / Feature Flags / Load Generator) — GIỮ PRIVATE
```
kubectl -n techx-tf3 port-forward svc/frontend-proxy 8080:8080
```
Rồi mở trên máy bạn:
| UI | URL |
|---|---|
| Storefront (local) | http://localhost:8080/ |
| Grafana | http://localhost:8080/grafana/ |
| Jaeger (traces) | http://localhost:8080/jaeger/ui/ |
| Feature Flags UI | http://localhost:8080/feature/ |
| Load Generator | http://localhost:8080/loadgen/ |

> ⚠️ **KHÔNG** patch Service sang LoadBalancer / expose ops UI ra public. Grafana bật anonymous-admin
> mặc định — public là ai cũng vào admin được. Chỉ dùng port-forward.

---

## Lưu ý an toàn (mọi nhóm phải theo)
- **KHÔNG** đụng flagd (gỡ/đổi URI/token nguồn `flags.json`) — vi phạm = disqualify cả TF3.
- **KHÔNG** commit secret thật (flagd token / AWS key) vào file tracked.
- Ops private, storefront public. Đây là env chạy song song để làm mandate trong lúc account BTC bị hold.

## Sự cố hay gặp
- `Unauthorized` khi `kubectl`: ARN chưa được cấp access entry → xem B0 mục 2.
- Tunnel mở nhưng `kubectl` timeout: quên chạy B2 (server vẫn trỏ endpoint thật, không phải localhost:8443).
- `TargetNotConnected` khi start-session: bastion chưa đăng ký SSM / sai instance id.
