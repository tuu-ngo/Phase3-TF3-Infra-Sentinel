# REL-17 — Truy cập EKS API + UI vận hành qua Cloudflare Zero Trust (thay dần SSM bastion)

**Trạng thái hiện tại (đã live):** domain đang dùng là `arthur-ngo.org` (domain cá nhân đã có sẵn
trong account Cloudflare — xem ghi chú "domain cá nhân" ở cuối file trước khi dùng làm bằng chứng
mandate chính thức). Đã có 4 route đang chạy:

| Route | URL | Đích |
|---|---|---|
| kubectl (TCP, qua EKS API) | `kubectl.arthur-ngo.org` | EKS API server — vẫn cần AWS IAM/EKS access entry riêng, xem giải thích ở Phần D |
| Grafana | `https://grafana.arthur-ngo.org` | thẳng vào Service trong cluster, **không cần IAM** |
| Jaeger | `https://jaeger.arthur-ngo.org` | thẳng vào Service trong cluster, **không cần IAM** |
| ArgoCD | `https://argocd.arthur-ngo.org` | thẳng vào Service trong cluster, **không cần IAM** (chặng nội bộ tới `argocd-server` bỏ qua verify TLS vì cert tự ký — xem `no_tls_verify` trong `internal_ui_routes`) |

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

Giao diện hiện tại của Cloudflare dùng **policy theo resource scope** (không còn tab Account/Zone
tách riêng như tài liệu cũ) — mỗi token cần **2 policy** vì 2 nhóm quyền khác phạm vi resource:

1. dash.cloudflare.com → **My Profile → API Tokens → Create Token → Create Custom Token**
   (đừng dùng template có sẵn — không cái nào khớp đủ 3 quyền cần).
2. **Policy 1 — quyền cấp account** (Tunnel + Access): ở dropdown resource scope (mặc định đang
   là **"Entire Account"**, giữ nguyên, KHÔNG đổi sang "Specified Domains" cho policy này) →
   thêm 2 permission:
   - Tìm theo từ khoá `Connector` hoặc `Tunnel` — tên nhóm quyền này Cloudflare đã đổi, hiện tại
     là **"Cloudflare One Connectors"** hoặc **"Cloudflare One Connector: cloudflared"** (tên cũ
     "Cloudflare Tunnel" có thể không còn hiện) → chọn **Edit**.
   - `Access: Apps and Policies` → **Edit**.
3. Bấm **"+ Add more"** / **"Add policy"** bên dưới để thêm **Policy 2 — quyền DNS riêng zone**:
   đổi resource scope của policy này từ "Entire Account" sang **"Specified Domains"** → chọn đúng
   domain vừa tạo ở A1. Chỉ sau khi đổi sang "Specified Domains" thì danh mục quyền mới đổi từ
   cấp account sang cấp zone — lúc đó cuộn tới **DNS & Zones** sẽ thấy dòng **"DNS"** (khác với
   "Account DNS Settings" thấy ở policy Entire Account) → chọn **Edit**.
4. Nếu Policy 1 vẫn không thấy quyền Tunnel/Connector nào: khả năng Zero Trust chưa active xong
   (quay lại A2 trước).
5. Copy token — **không dán vào file trong repo**. Set làm biến môi trường lúc cần apply:

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

## Phần D — Team dùng hằng ngày

Có **2 kiểu truy cập** khác hẳn nhau về độ đơn giản — chọn đúng cái cần, đừng dùng nhầm cái nặng
hơn nếu chỉ cần xem UI.

### D1. Xem Grafana/Jaeger/ArgoCD — chỉ cần mở link, không cần cài gì

Không cần `cloudflared` client, không cần AWS IAM, không cần terminal nào cả:

1. Mở trình duyệt, vào thẳng: `https://grafana.arthur-ngo.org`, `https://jaeger.arthur-ngo.org`,
   hoặc `https://argocd.arthur-ngo.org`.
2. Lần đầu (hoặc sau khi session hết hạn — mặc định 8h) sẽ bị redirect sang trang đăng nhập SSO
   của Cloudflare Access → đăng nhập bằng email đã được cấp quyền.
3. Đăng nhập xong, thấy thẳng UI — xong.

Đây chính là cách trả lời câu hỏi mentor về "đơn giản hoá, dùng domain, không cần cert".

### D2. `kubectl` thật (thao tác cluster, không chỉ xem) — vẫn cần `cloudflared` client + IAM

`kubectl` gọi thẳng EKS API server, mà **bản thân EKS luôn đòi hỏi danh tính AWS IAM riêng** để xác
thực API call — Cloudflare chỉ lo phần "ai tới được cổng vào mạng", không thay được bước IAM này.
Người dùng cần đã có EKS access entry + K8s RBAC từ trước (như mentor-mandate-reviewer, hoặc IAM
user thường của team), rồi:

Cài `cloudflared` local 1 lần (`brew install cloudflared` / tải binary từ
github.com/cloudflare/cloudflared/releases), sau đó:

```sh
cloudflared access tcp --hostname kubectl.arthur-ngo.org --url 127.0.0.1:8443
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

### D3. Thêm UI mới vào danh sách route trực tiếp (D1)

Sửa `internal_ui_routes` trong `infra/live/production/cloudflare-access.tf` — thêm 1 entry
`{ hostname = "<tên>.arthur-ngo.org", service = "http://<service>.<namespace>.svc.cluster.local:<port>" }`,
`terraform apply` lại (`-target="module.cloudflare_access"` để an toàn, không đụng resource khác).
Không cần sửa gì phía `cloudflared` Deployment — 1 tunnel phục vụ được nhiều route cùng lúc.

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

## Ghi chú — domain cá nhân, cân nhắc trước khi dùng làm bằng chứng mandate

`arthur-ngo.org` là domain cá nhân có sẵn trong account Cloudflare dùng để dựng nhanh (team chưa
mua domain riêng cho dự án). Dùng được cho vận hành nội bộ team, nhưng **chưa nên dùng làm route
chính thức để nộp bằng chứng Mandate #1 cho mentor** — Mandate #1 hiện đã đạt độc lập qua route
Envoy đã gỡ + runbook SSM (`private-access-to-ops-uis.md`, dùng IAM role scoped riêng cho mentor,
không dính domain cá nhân). Nếu muốn dùng Cloudflare Access làm đường chính thức luôn, cần: (1) đổi
sang domain thuộc sở hữu team/dự án, (2) thêm email mentor vào Access Policy (hiện chỉ có
`hiimtuu@gmail.com`).
