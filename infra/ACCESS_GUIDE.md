# Hướng dẫn truy cập cluster — SSM Bastion

Từ 09/07, EKS API của `techx-corp-tf3` đã chuyển sang **private-only**
(`cluster_endpoint_public_access = false`) — không còn IP nào được allowlist trực tiếp nữa.
Lý do: bị đè mất CIDR allowlist 2 lần do nhiều người tự `terraform apply` với `tfvars` khác nhau
(xem `CLAUDE.md` + `docs/postmortem/`). Từ giờ, mọi truy cập `kubectl`/`helm` đi qua **SSM
bastion** — xác thực bằng IAM, không phải theo địa chỉ IP, nên không ai cần "xin thêm IP" nữa.

---

## Chuẩn bị (làm 1 lần trên mỗi máy)

### 1. AWS CLI v2
```sh
aws --version   # phải ra aws-cli/2.x
```
Chưa có thì tải tại: https://aws.amazon.com/cli/

### 2. Session Manager Plugin — bắt buộc, hay bị quên nhất

`aws ssm start-session` sẽ báo lỗi `SessionManagerPlugin is not found` nếu thiếu.

- **Windows**: tải `SessionManagerPluginSetup.exe` tại
  https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html,
  chạy installer.
- **Mac**: `brew install --cask session-manager-plugin`
- **Linux**: tải `.deb`/`.rpm` theo link ở trên.

Kiểm tra cài xong:
```sh
session-manager-plugin --version
```

### 3. Cấu hình AWS credentials đúng IAM user của mình

```sh
aws configure --profile techx-corp
# Access Key ID / Secret Access Key của đúng user (arthur / CDO01 / CDO02 / AIO02)
# Region: ap-southeast-1
```

Dùng profile này cho mọi lệnh sau, ví dụ set biến môi trường cho cả session:
```sh
export AWS_PROFILE=techx-corp
```

---

## Dùng hằng ngày — 2 bước

### Bước 1 — Mở tunnel (giữ terminal này chạy, đừng đóng)

```sh
aws ssm start-session \
  --target i-0ed38bc9cd8c4c2b0 \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters host="78F80EEA7B05283C4A1AD20C546A4559.gr7.ap-southeast-1.eks.amazonaws.com",portNumber="443",localPortNumber="8443" \
  --region ap-southeast-1
```

Thành công khi thấy:
```
Starting session with SessionId: <ten-user>-xxxxxxxxxxxxx
Port 8443 opened for sessionId xxxxxxxxxxxxx.
Waiting for connections...
```
Để yên terminal này, không gõ gì thêm — đây là tunnel đang chạy nền.

> Lệnh đầy đủ (tự điền sẵn ID/endpoint hiện tại) luôn lấy lại được bằng:
> ```sh
> cd infra/live/production && terraform output ssm_tunnel_command
> ```

### Bước 2 — Terminal MỚI: cấu hình kubectl (chỉ cần làm 1 lần)

```sh
aws eks update-kubeconfig --name techx-corp-tf3 --region ap-southeast-1

kubectl config set-cluster arn:aws:eks:ap-southeast-1:197826770971:cluster/techx-corp-tf3 \
  --server=https://localhost:8443 \
  --insecure-skip-tls-verify=true
```

`--insecure-skip-tls-verify` cần thiết vì chứng chỉ TLS của cluster cấp cho hostname thật, không
phải `localhost` — chấp nhận được vì traffic đã đi trong tunnel mã hoá của SSM, không lộ ra ngoài.

### Từ đây, dùng `kubectl`/`helm` bình thường (mỗi khi tunnel ở Bước 1 đang mở)

```sh
kubectl get pods -n techx-tf3
kubectl get nodes
helm list -n techx-tf3
kubectl -n techx-tf3 port-forward svc/frontend-proxy 8080:8080   # để mở storefront/Grafana/Jaeger
```

### Dùng xong

Bấm `Ctrl+C` ở terminal Bước 1 để đóng tunnel. Không cần dọn gì thêm — không có state nào lưu lại
phía client.

---

## Lỗi hay gặp

| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| `SessionManagerPlugin is not found` | Chưa cài plugin | Làm lại mục Chuẩn bị #2 |
| `AccessDeniedException` khi `start-session` | Sai IAM credential / chưa đủ quyền SSM | Kiểm tra `aws sts get-caller-identity` ra đúng user chưa; 4 user hiện tại đều `AdministratorAccess` nên đủ quyền nếu đúng identity |
| `kubectl`: `connection refused` tới `localhost:8443` | Quên mở tunnel (Bước 1), hoặc tunnel đã đóng | Mở lại Bước 1, giữ terminal chạy song song với terminal `kubectl` |
| `x509: certificate is valid for ..., not localhost` | Quên `--insecure-skip-tls-verify=true` | Chạy lại đúng lệnh `kubectl config set-cluster` ở Bước 2 |
| Tunnel tự ngắt sau một lúc không thao tác | SSM timeout khi rảnh quá lâu | Mở lại Bước 1, không mất dữ liệu gì |
| `TargetNotConnected` | Bastion instance chưa đăng ký xong với SSM (mới tạo) hoặc đang khởi động lại | Đợi 1-2 phút, kiểm tra `aws ssm describe-instance-information` thấy `PingStatus: Online` |

---

## Thông tin tham chiếu nhanh

| Giá trị | Nội dung |
|---|---|
| Bastion instance ID | `i-0ed38bc9cd8c4c2b0` |
| Cluster endpoint (không có `https://`) | `78F80EEA7B05283C4A1AD20C546A4559.gr7.ap-southeast-1.eks.amazonaws.com` |
| Region | `ap-southeast-1` |
| Cluster name | `techx-corp-tf3` |
| Namespace ứng dụng | `techx-tf3` |

> Nếu bastion bị destroy/tạo lại (VD sau khi `terraform apply` đổi hạ tầng), 2 giá trị đầu có thể
> đổi — luôn lấy lại bằng `terraform output bastion_instance_id` và `terraform output cluster_endpoint`
> thay vì tin vào bảng này nếu thấy không khớp.

---

## Vì sao đổi sang cách này (bối cảnh, xem thêm `docs/postmortem/`)

Trước đây, EKS API public + giới hạn theo CIDR (`allowed_admin_cidrs` trong `terraform.tfvars`).
Vấn đề: file này không sync qua git (gitignored), nên khi 2+ người cùng `terraform apply` từ máy
riêng với `tfvars` khác nhau, người apply sau **ghi đè mất** toàn bộ danh sách IP người trước đã
thêm — xảy ra thật 2 lần trong cùng 1 ngày (08/07), có lúc khiến chính người quản trị (`arthur`)
bị khoá ngoài. Giải pháp SSM bastion loại bỏ hoàn toàn khái niệm "IP allowlist" — không còn gì để
bị ghi đè hay đồng bộ sai nữa.
