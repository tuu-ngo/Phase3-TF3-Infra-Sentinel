# ADR 0004 — Mandate #1 (cổng vận hành riêng tư): phần CDO01 (Security — least-exposure Envoy)

**Ngày:** 13/07/2026
**Người quyết định (ký):** CDO01 (Performance Efficiency + Security)
**Directive:** [`mandates/MANDATE-01-network-exposure.md`](../../phase3%20-%20information/mandates/MANDATE-01-network-exposure.md) — hạn **14/07/2026**
**Liên quan:** PR #48 (`docs/mandate-01-cdo02-response`) — ADR 0003 (CDO02), chưa merge vào `main`
**Trạng thái:** 🔴 Chưa thực thi — có 1 blocker hạ tầng phải xử lý trước (mục "CẢNH BÁO" bên dưới) + tài khoản AWS đang bị hold (postmortem 0002)

---

## 0. Đã đọc PR #48 — tóm tắt để khỏi phải mở lại

PR #48 (nhánh `docs/mandate-01-cdo02-response`, tác giả `tuu-ngo`) là phần **CDO02** nộp cho Mandate #1. Nó
**không đụng route Envoy nào cả** — đúng như PR tự khai phạm vi ("Phần least-exposure Envoy là Security/CDO01").
3 file nó thêm:

1. `docs/adr/0003-mandate-01-private-ops-cdo02.md` — ADR ký bởi CDO02, cam kết 3 việc: cắt chuyển
   zero-downtime, change-mgmt/rollback/runbook, audit log truy cập bastion. ADR này **xác nhận hiện trạng
   phơi bày** (đọc trực tiếp từ Envoy config, khớp với những gì mình tự đọc lại ở mục 2 dưới): `/grafana`,
   `/jaeger/ui`, `/loadgen`, `/feature` (flagd-ui) đang public qua `frontend-proxy`. ArgoCD đã ClusterIP-only
   sẵn, không cần đụng.
2. `docs/runbooks/private-access-to-ops-uis.md` — runbook SSM bastion + `kubectl port-forward` cho
   team/mentor vào Grafana/Jaeger/ArgoCD sau khi route công khai bị gỡ.
3. `infra/ssm-session-logging.tf` — CloudWatch log group + IAM policy để ghi vết mọi phiên SSM bastion
   (bằng chứng Auditability: ai vào, khi nào).

Việc thật sự phải làm (gỡ route khỏi Envoy) **chưa ai làm** — đó là lý do file này tồn tại.

### ⚠️ CẢNH BÁO — phải xử lý TRƯỚC khi `terraform apply` bất kỳ thứ gì trong `infra/`, kể cả PR #48

Đọc kỹ Terraform plan đính kèm trong comment CI của PR #48 (`infra/`), thấy plan sẽ **update in-place**
`aws_cloudfront_distribution.frontend` theo hướng **xấu đi**, không liên quan gì đến nội dung PR:

```
~ aliases = [ - "nvtank.dev" ]                                  # mất custom domain
~ default_cache_behavior.function_association {
    - function_arn = ".../function/block-internal-paths" -> null  # XOÁ CloudFront Function này
  }
~ viewer_certificate {
    - acm_certificate_arn = "..." -> null                         # mất ACM cert riêng
    ~ cloudfront_default_certificate = false -> true
    ~ minimum_protocol_version = "TLSv1.2_2021" -> "TLSv1"         # hạ TLS xuống bản cũ/không an toàn
    - ssl_support_method = "sni-only" -> null
  }
```

Đã `grep` toàn repo (`infra/*.tf`, mọi doc) — **không có chỗ nào định nghĩa** `block-internal-paths`,
`nvtank.dev`, hay ACM cert cho CloudFront. `infra/cloudfront.tf` hiện tại chỉ có
`cloudfront_default_certificate = true`, không alias, không function association. Nghĩa là:

- Có ai đó đã **tạo tay** (console/CLI, ngoài Terraform) một CloudFront Function tên `block-internal-paths`
  và gắn vào distribution — cái tên gợi ý **đây rất có thể chính là cơ chế đang chặn các path nội bộ ở
  edge** (có thể đang là lớp bảo vệ *duy nhất* cho `/grafana`, `/jaeger`, `/feature` nếu route Envoy vẫn
  còn public) — cộng thêm 1 domain riêng + ACM cert, cũng tạo tay.
- Vì các thứ đó **không có trong `infra/cloudfront.tf`**, bất kỳ `terraform apply` nào từ state hiện tại
  (không riêng gì PR #48 — main cũng vậy) sẽ **xoá `block-internal-paths` + domain + ACM cert**, hạ
  `minimum_protocol_version` xuống `TLSv1` (giao thức cũ, có lỗ hổng đã biết, không đạt chuẩn bảo mật
  hiện đại). Ngay trước hạn chấm Mandate #1 (an ninh mạng), đây là hướng đi **ngược lại hoàn toàn** tinh
  thần directive.

**Việc phải làm trước, không thương lượng:**
1. Xác minh với người đã tạo `block-internal-paths` (khả năng cao là ai đó bên CDO02, vì ADR 0003 xác
   nhận exposure hiện trạng bằng cách "đọc config Envoy" chứ không nhắc gì tới CloudFront Function này —
   có thể là việc ai đó tự vá tạm ở edge, làm ngoài git).
2. **Import** function + alias + cert vào `infra/cloudfront.tf` (`terraform import`) để state khớp thực
   tế, **hoặc** quyết định tường minh giữ/bỏ (ghi rõ trong ADR này), rồi mới `apply` bất cứ thứ gì —
   kể cả `infra/ssm-session-logging.tf` của PR #48.
3. Cho tới khi xong bước 1-2: **không chạy `terraform apply`** trên `infra/` (kể cả nhánh PR #48), chỉ
   `terraform plan` để soi drift.

Việc gỡ route ở tầng Envoy (mục 3 dưới) **không phụ thuộc** vào việc dọn drift CloudFront này — có thể làm
song song — nhưng **deploy hạ tầng Terraform thì phải chặn lại** cho tới khi dọn xong, nếu không mọi công
sức gỡ route Envoy sẽ vô nghĩa (edge protection bị xoá, hoặc tệ hơn là TLS bị hạ cấp) mà không ai để ý vì
nó nằm trong "Plan: 4 to add, 1 to change" — dễ lướt qua giữa hàng trăm dòng plan.

---

## 1. Bối cảnh

Mandate #1 (`MANDATE-01-network-exposure.md`, hiệu lực ngay, hạn **14/07/2026**): storefront giữ public;
**mọi cổng vận hành/nội bộ** (Grafana, Jaeger, ArgoCD, mọi dashboard/control-plane tương tự) phải riêng tư
— không giới hạn danh sách liệt kê. Ràng buộc: không đứt storefront/SLO, trong ngân sách, **không đụng
flagd**. Phải nộp: cách truy cập riêng tư cho mentor tự vào chấm.

## 2. Hiện trạng phơi bày — tự xác minh lại từ `src/frontend-proxy/envoy.tmpl.yaml`

`frontend-proxy` (Envoy) là **cổng public duy nhất** (`values-ingress.yaml`: chỉ `frontend-proxy` có
`ingress.enabled: true`, ALB `internet-facing`; Grafana/Jaeger tự thân là ClusterIP, không có ingress
riêng — nên gỡ route ở Envoy là **đủ** để cắt truy cập public, không cần đụng gì khác). Route hiện tại
(`envoy.tmpl.yaml`, virtual host `frontend`, khớp domain `"*"`):

| Path | Cluster | Thuộc diện Mandate #1? |
|---|---|---|
| `/loadgen`, `/loadgen/` | `loadgen` (Locust UI) | Có — UI vận hành nội bộ, lộ thông tin load test |
| `/otlp-http/` | `opentelemetry_collector_http` | **Không** — endpoint OTLP ingest cho browser RUM (frontend gửi trace/metric từ trình duyệt khách), không phải UI vận hành |
| `/jaeger`, `/jaeger/` | `jaeger` | **Có** — nêu đích danh trong mandate |
| `/grafana`, `/grafana/` | `grafana` | **Có** — nêu đích danh trong mandate (Grafana đang anonymous-admin, mức độ nghiêm trọng cao nhất) |
| `/images/` | `image-provider` | Không — ảnh sản phẩm, thuộc storefront |
| `/flagservice/` | `flagservice` | **KHÔNG ĐƯỢC ĐỤNG** — đây là kênh service đọc flag runtime (flagd), gỡ/redirect là **disqualify** theo luật chơi (`CLAUDE.md` + mandate mục Ràng buộc) |
| `/feature` | `flagd-ui` | Có — đây là **UI người** để bật/tắt flag, khác với `/flagservice` (kênh máy đọc flag). Gỡ UI này an toàn, không ảnh hưởng cơ chế flagd |
| `/` (catch-all) | `frontend` | Không — storefront, giữ nguyên |

ArgoCD: đã xác nhận ClusterIP-only (không có route Envoy, không Ingress riêng) — đã đạt yêu cầu mandate
sẵn, không cần làm gì thêm ở đây; chỉ cần đảm bảo runbook truy cập port-forward (PR #48 đã có) hoạt động.

**Filter không được đụng:** `envoy.filters.http.fault` (fault-injection, `max_active_faults: 100`) — hạ
tầng nhạy cảm dùng cho sự cố BTC bơm vào, tương tự flagd. Không xoá/sửa khi tối ưu file này.

## 3. Quyết định (phần CDO01)

Gỡ khỏi `route_config` trong `src/frontend-proxy/envoy.tmpl.yaml` (đường dẫn thật trong
`techx-corp-platform`, không phải file lý thuyết):

- `/jaeger` + `/jaeger/` (route + redirect)
- `/grafana` + `/grafana/` (route + redirect)
- `/feature` (flagd-ui)
- `/loadgen` + `/loadgen/`

Giữ nguyên: `/flagservice/`, `/otlp-http/`, `/images/`, `/`, toàn bộ `http_filters` (kể cả
`envoy.filters.http.fault`), toàn bộ `access_log`.

> Route này **hard-code trong file template, không phải Helm value** — sửa xong phải **rebuild + push lại
> image `frontend-proxy`**, không phải chỉ sửa `values.yaml`. Xem bước thực thi.

## 4. Các bước thực thi

### Bước 0 — dọn drift CloudFront (mục CẢNH BÁO ở trên)
Làm trước hoặc song song, nhưng **không** để ai chạy `terraform apply` (kể cả merge PR #48) trước khi
xong. Nếu không rõ ai tạo `block-internal-paths`, hỏi trong kênh TF3 trước khi quyết định import hay bỏ.

### Bước 1 — kiểm tra tài khoản AWS đã được mở lại chưa
Xem `docs/postmortem/0002-account-hold-and-bastion-loss.md` +
`docs/runbooks/eks-recovery-after-account-unblock.md` (nhánh `docs/incident-account-hold`, chưa merge
`main` — merge trước hoặc `git fetch` để đọc). Account đang hold từ 12/07; nếu vẫn hold, chuẩn bị code
(bước 2-5) làm được, nhưng **build/push image + deploy thật (bước 6-8) phải chờ account mở** — đúng tình
trạng PR #48 đang gặp.

### Bước 2 — sửa route
Sửa `techx-corp-platform/src/frontend-proxy/envoy.tmpl.yaml`, xoá 4 route/redirect ở mục 3. Không đổi gì
khác trong file (giữ nguyên format, filter, access_log).

### Bước 3 — build + smoke test local
```sh
cd techx-corp-platform
make build            # hoặc: make redeploy service=frontend-proxy nếu stack đang chạy local
make start             # hoặc restart frontend-proxy
curl -i http://localhost:8080/            # 200 — storefront
curl -i http://localhost:8080/grafana     # phải 404 (route không còn tồn tại)
curl -i http://localhost:8080/jaeger      # 404
curl -i http://localhost:8080/feature     # 404
curl -i http://localhost:8080/flagservice/ # PHẢI vẫn hoạt động bình thường — nếu lỗi, dừng lại
```

### Bước 4 — build multi-arch + push lên ECR của TF3
```sh
# .env.override đã trỏ IMAGE_NAME về ECR riêng của TF3 (012619468490.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp)
./deploy/build-push-images.sh    # smoke-build checkout trước, rồi build+push multi-arch toàn bộ, gồm frontend-proxy
```
Ghi lại tag image mới (thường là git short-SHA, theo cách `values-prod.yaml` đang dùng `tag: d2bc367`).

### Bước 5 — cập nhật GitOps, đi qua PR (không sửa tay cluster)
Sửa `deploy/values-prod.yaml` (hoặc field tag tương ứng) sang tag mới build ở bước 4. Commit cả
`envoy.tmpl.yaml` + `values-prod.yaml` trong 1 branch, mở PR (status check `gitleaks` phải xanh — hook đã
cài qua `scripts/setup-hooks.sh`). Nhờ **CDO02 review diff xác nhận `/flagservice` không bị đụng** — đúng
gạch đầu dòng CDO02 đã ghi trong ADR 0003 ("CDO02 review diff xác nhận flagd an toàn").

### Bước 6 — merge → ArgoCD tự sync
`gitops/apps/techx-corp.yaml` đã bật `syncPolicy.automated.{prune,selfHeal}` — merge vào `main` là đủ,
ArgoCD tự pick up. Theo dõi rollout:
```sh
kubectl -n techx-tf3 rollout status deploy/frontend-proxy
kubectl -n techx-tf3 get pdb frontend-proxy-pdb    # minAvailable:1, phải luôn ≥1 pod Ready trong lúc rollout
```
`frontend-proxy` đã có `replicas: 2` (`values-prod.yaml`) + PDB `frontend-proxy-pdb`
(`gitops/infrastructure/pdb-checkout.yaml`) sẵn — rolling update không đứt storefront, không cần thêm gì.

### Bước 7 — verify evidence (khớp mục evidence ADR 0003, cho mentor)
```sh
curl -i https://<cloudfront-domain>/            # 200 — storefront public
curl -i https://<cloudfront-domain>/grafana     # 403/404 — không còn public
curl -i https://<cloudfront-domain>/jaeger      # 403/404
curl -i https://<cloudfront-domain>/feature     # 403/404
curl -i https://<cloudfront-domain>/loadgen     # 403/404
curl -i https://<cloudfront-domain>/flagservice/health  # vẫn phải hoạt động (nếu service có health path)
```
Theo runbook `docs/runbooks/private-access-to-ops-uis.md` (PR #48): mở SSM tunnel + `kubectl
port-forward svc/grafana` / `svc/jaeger` → xác nhận vào được qua đường riêng. Kiểm SLO checkout trên
Grafana không tụt dưới 99% trong cửa sổ cắt chuyển.

### Bước 8 — deploy `infra/ssm-session-logging.tf` (sau khi Bước 0 xong)
Sau khi drift CloudFront đã dọn (Bước 0) và account đã mở (Bước 1), `terraform apply` phần CDO02 để bật
audit log SSM bastion — hoàn tất chân Auditability của mandate.

## 5. Rollback

- Envoy: `git revert` commit ở Bước 5 → PR → merge → ArgoCD re-sync → route công khai trở lại. Phát hiện
  sự cố qua smoke test Bước 3/7 lặp lại ngay sau sync.
- Image: tag cũ (`d2bc367` hoặc tag trước đó) vẫn còn trong ECR — revert `values-prod.yaml` về tag đó nếu
  cần rollback nhanh hơn build lại.
- Không có thay đổi schema/data — rollback không rủi ro mất dữ liệu.

## 6. Trạng thái thực thi

- [ ] Bước 0: xác minh nguồn gốc + import/quyết định `block-internal-paths`/`nvtank.dev`/ACM cert vào Terraform
- [ ] Bước 1: xác nhận account AWS đã mở (postmortem 0002)
- [ ] Bước 2: sửa `envoy.tmpl.yaml`
- [ ] Bước 3: smoke test local
- [ ] Bước 4: build + push image
- [ ] Bước 5: PR (gitleaks xanh) + CDO02 review diff flagd
- [ ] Bước 6: merge, ArgoCD sync, rollout không đứt storefront
- [ ] Bước 7: evidence 1-6 + SLO checkout ≥99%
- [ ] Bước 8: deploy SSM session logging (CDO02, sau Bước 0)
- [ ] Mời mentor verify

---
*Ký: CDO01. Phối hợp: CDO02 (Reliability/Ops/Auditability — ADR 0003, PR #48). Blocker phải xử lý trước
Bước 6 trở đi: drift CloudFront (mục 0) và account AWS hold (postmortem 0002).*
