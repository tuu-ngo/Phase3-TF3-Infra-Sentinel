# REL-17 — Truy cập EKS API qua Cloudflare Zero Trust (thay dần SSM bastion)

Bổ sung, **không thay thế ngay**, cho `docs/runbooks/private-access-to-ops-uis.md` / SSM bastion.
Xem lý do + đánh giá phương án ở `docs/backlog/cdo02-reliability-cost-backlog.md` (REL-17). SSM
bastion giữ nguyên hoạt động suốt quá trình triển khai — không có bước nào ở đây tắt nó.

**Kiến trúc:** `cloudflared` chạy như 1 Deployment ngay trong cluster (`techx-tf3`), tự nối ra
Cloudflare edge (outbound-only, **0 inbound port** — giữ nguyên posture bảo mật của SSM bastion).
Người dùng cài `cloudflared` local, đăng nhập SSO, tunnel về máy mình — thay `aws ssm
start-session` bằng `cloudflared access tcp`.

## Phần A — Bạn tự làm (không thể tự động qua Claude Code)

Lý do: tạo tài khoản + nhập thông tin xác thực nằm ngoài phạm vi hành động được phép tự động hóa.

### A1. Mua domain + add vào Cloudflare

1. Mua 1 domain rẻ — khuyến nghị qua **Cloudflare Registrar** (domain tự động on Cloudflare NS,
   không phải chờ propagate DNS registrar ngoài): dash.cloudflare.com → **Domain Registration**.
   Domain gợi ý dạng: `techx-tf3-ops.<tld rẻ, vd .xyz/.dev>`.
2. Nếu mua ở registrar khác: **Add a Site** trong Cloudflare dashboard → trỏ nameserver domain đó
   sang NS Cloudflare cấp → có thể mất vài phút tới vài giờ để active, **không apply Terraform tới
   khi zone status = Active**.
3. Ghi lại: **Zone ID** (Overview page của domain, cột phải) và tên domain chính xác.

### A2. Bật Zero Trust + liên kết SSO

1. dash.cloudflare.com → **Zero Trust** → chọn tên team (VD `techx-tf3`) → đây chính là
   `<team>.cloudflareaccess.com`, dùng free tier (đủ ≤50 user, không cần thẻ).
2. **Settings → Authentication → Login methods** → thêm **Google Workspace** hoặc **GitHub**
   (dùng SSO/org sẵn có của team) → theo hướng dẫn OAuth app trên màn hình.
3. Ghi lại **Account ID** (Zero Trust → bất kỳ trang nào, góc phải, hoặc dash.cloudflare.com →
   trang chủ domain → cột phải "Account ID").

### A3. Tạo API Token cho Terraform

1. dash.cloudflare.com → **My Profile → API Tokens → Create Token**.
2. Dùng template **"Edit zero trust"** hoặc **Custom token** với quyền tối thiểu:
   - `Account` → `Cloudflare Tunnel:Edit`, `Access: Apps and Policies:Edit`
   - `Zone` → `DNS:Edit` (scope đúng zone vừa tạo ở A1)
3. Copy token — **không dán vào file trong repo**. Set làm biến môi trường lúc cần apply:

   ```sh
   export CLOUDFLARE_API_TOKEN="<token vừa copy>"
   ```

### A4. Gửi lại cho Claude Code (qua chat, không phải file)

Để mình điền `terraform.tfvars`/chạy apply, cần bạn cung cấp (không nhạy cảm, không phải secret):
- Account ID
- Zone ID + tên domain
- Hostname muốn dùng cho tunnel, VD `kubectl.techx-tf3-ops.xyz`
- Email domain của team để cấu hình Access policy (VD `@yourcompany.com`), hoặc danh sách email
  cụ thể nếu không có domain công ty dùng chung

## Phần B — Terraform apply (Claude Code làm khi có đủ thông tin ở A4 + token ở A3)

```sh
cd infra/live/production
export CLOUDFLARE_API_TOKEN="..."   # từ A3, KHÔNG commit
terraform init -reconfigure -backend-config=backend.hcl.example

terraform plan -lock=false \
  -var="enable_cloudflare_access=true" \
  -var="cloudflare_account_id=<A4>" \
  -var="cloudflare_zone_id=<A4>" \
  -var="cloudflare_zone_name=<A4>" \
  -var="cloudflare_tunnel_hostname=<A4>" \
  -var="cloudflare_allowed_email_domain=<A4>" \
  -out=tfplan

terraform apply tfplan
```

Sau khi apply, lấy tunnel token (sensitive, không in ra log CI/chat công khai):

```sh
terraform output -raw cloudflare_tunnel_token
```

## Phần C — Đưa token vào cluster + verify

```sh
kubectl -n techx-tf3 create secret generic cloudflared-tunnel-credentials \
  --from-literal=token="$(terraform output -raw cloudflare_tunnel_token)"
```

`gitops/infrastructure/cloudflared.yaml` (đã merge qua ArgoCD trước đó, chạy sẵn nhưng
`CrashLoopBackOff`/`CreateContainerConfigError` cho tới bước này — bình thường, không phải lỗi)
sẽ tự pick up Secret và lên `Running` trong ~30s:

```sh
kubectl -n techx-tf3 get pods -l app.kubernetes.io/name=cloudflared
kubectl -n techx-tf3 logs -l app.kubernetes.io/name=cloudflared --tail=20
```

Log mong đợi: `Registered tunnel connection` — nghĩa là cloudflared đã nối ra edge thành công.

## Phần D — Team dùng hằng ngày (thay `aws ssm start-session`)

Mỗi người cài `cloudflared` local 1 lần (`brew install cloudflared` / tải binary từ
github.com/cloudflare/cloudflared/releases), sau đó:

```sh
cloudflared access tcp --hostname <tunnel_hostname từ A4> --url 127.0.0.1:8443
```

Lệnh trên tự mở trình duyệt cho đăng nhập SSO (lần đầu, hoặc khi session hết hạn theo
`session_duration` đã cấu hình, mặc định 8h — dài hơn nhiều so với SSM tunnel ~10-20 phút idle).
Sau đó, y hệt cách dùng SSM bastion trước đây:

```sh
aws eks update-kubeconfig --name techx-corp-tf3 --region ap-southeast-1
kubectl config set-cluster arn:aws:eks:ap-southeast-1:197826770971:cluster/techx-corp-tf3 \
  --server=https://localhost:8443 --insecure-skip-tls-verify=true
kubectl get pods -n techx-tf3
```

## Rollback

Không có gì buộc phải giữ — đây là bổ sung song song:

```sh
kubectl -n techx-tf3 delete -f gitops/infrastructure/cloudflared.yaml
kubectl -n techx-tf3 delete secret cloudflared-tunnel-credentials
```

Hoặc tắt hẳn ở tầng Terraform: `-var="enable_cloudflare_access=false"` rồi `apply` — xoá tunnel +
Access application + DNS record trên Cloudflare, không ảnh hưởng gì tới EKS/VPC/SSM bastion.

## Verify (acceptance criteria REL-17)

- [ ] `cloudflared access tcp ...` + `kubectl get pods -n techx-tf3` chạy được, không cần
      `aws ssm start-session`.
- [ ] Đăng nhập SSO đúng identity người dùng (không phải IAM user chung) — kiểm qua Zero Trust →
      **Logs → Access** thấy đúng email người vừa đăng nhập.
- [ ] SSM bastion vẫn hoạt động song song, không bị đụng.
- [ ] Sau ≥1 tuần vận hành ổn định, đánh giá lại có nên tắt/giữ SSM bastion làm fallback lâu dài
      hay không (không tự tắt trong runbook này).
