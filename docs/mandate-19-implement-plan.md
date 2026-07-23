# Kế hoạch triển khai [MANDATE-19]: Biết trần & Nâng trần bằng hiệu suất

## Mục tiêu

Directive #19 yêu cầu 4 thứ phải nộp:
1. **Tìm breakpoint thật** (RPS/user đỉnh mà SLO vẫn giữ) — trước và sau tuning
2. **Nâng trần, không thêm node** — chứng minh requests-per-node tăng sau khi tuning
3. **Xử nút thắt thông lượng** — tìm service bão hoà sớm nhất và nới nó
4. **Demo xuống mềm** — đẩy tải vượt trần → checkout vẫn sống, browse bị shed (429)

---

## Bối cảnh từ các Mandate trước

| Mandate | Kết quả liên quan |
|---|---|
| Mandate-02 | 200 user: p95 ~46ms, checkout 99.98%, node không đổi (7 node). Trần **chưa bị chạm**. |
| Mandate-16 | Checkout critical path song song hoá — latency giảm từ 185ms xuống ~45ms |

**Kết luận:** 200 user vẫn còn rất xa breakpoint thật. Hệ có headroom lớn chưa được khai thác.

---

## Thay đổi đã thực hiện

### 1. HPA Tuning — tăng requests-per-node density

**File:** [`gitops/infrastructure/hpa-hotpath.yaml`](file:///d:/Phase3_01/Phase3-TF3-Infra-Sentinel/gitops/infrastructure/hpa-hotpath.yaml)

| HPA | CPU target cũ | CPU target mới | maxReplicas cũ | maxReplicas mới |
|---|---|---|---|---|
| `frontend-proxy-hpa` | 65% | **75%** | 8 | 8 |
| `frontend-hpa` | 65% | **75%** | 8 | **12** |
| `product-catalog-hpa` | 65% | **75%** | 8 | **10** |
| `cart-hpa` | 65% | 65% (giữ) | 6 | 6 |
| `checkout-hpa` | 65% | 65% (giữ) | 8 | 8 |

**Lý do tăng target lên 75% cho browse services:** Mỗi pod gánh nhiều request hơn trước khi scale → cùng số node phục vụ được nhiều request hơn → requests-per-node tăng. Browse services không revenue-critical nên chấp nhận pod chạy nóng hơn.

**Lý do giữ 65% cho checkout/cart:** Revenue-critical — ưu tiên latency thấp hơn density.

### 2. Envoy Load Shedding — xuống mềm khi vượt trần

**File:** [`phase3 - information/techx-corp-platform/src/frontend-proxy/envoy.tmpl.yaml`](file:///d:/Phase3_01/Phase3-TF3-Infra-Sentinel/phase3%20-%20information/techx-corp-platform/src/frontend-proxy/envoy.tmpl.yaml)

#### 2a. Route split — checkout protected vs browse shedable

```
/otlp-http/    → collector           (giữ nguyên)
/images/       → image-provider      (giữ nguyên)
/flagservice/  → flagd               (KHÔNG đụng — Directive #1)
/api/checkout  → frontend            [checkout_protected — KHÔNG shed]
/              → frontend            [browse_shedable   — token bucket 150 RPS]
```

Route `/api/checkout` được đặt **trước** catch-all `/` để prefix match đúng ưu tiên.

#### 2b. `envoy.filters.http.local_ratelimit` filter

- Chạy **in-process** trong Envoy — không cần Redis external, không thêm latency đáng kể
- Global bucket: `10 000 token/s` — fallback, không bao giờ bị trigger thực tế
- Per-route override trên `browse_shedable`: `max_tokens=150, tokens_per_fill=150, fill_interval=1s`
- Khi browse vượt 150 RPS: Envoy trả HTTP 429 + header `x-local-rate-limit: true` ngay tại proxy — không đẩy xuống backend

#### 2c. Envoy circuit breaker `max_requests` tăng

- Cluster `frontend`: `max_requests: 1024 → 4096`
- Ngăn Envoy reject request ở tầng proxy trước khi backend thực sự cạn

### 3. ADR 0011

**File mới:** [`docs/adr/0011-mandate-19-throughput-ceiling-load-shedding.md`](file:///d:/Phase3_01/Phase3-TF3-Infra-Sentinel/docs/adr/0011-mandate-19-throughput-ceiling-load-shedding.md)

Ghi nhận: trần cũ/mới (placeholder — điền sau breakpoint test), nút thắt ở đâu, nâng bằng gì, cơ chế load-shedding.

---

## Kế hoạch Verification (người verify thực hiện)

### Bước 1 — Tìm breakpoint trước tuning (Phase 1)

> **Thực hiện TRƯỚC khi ArgoCD sync thay đổi HPA/Envoy**, hoặc dùng git stash để revert tạm thời.

```bash
# Ramp lên dần: 200 → 300 → 400 → 500 → 700 → 1000 user, giữ 3-5 phút mỗi bậc
kubectl -n techx-tf3 set env deploy/load-generator \
  LOCUST_USERS=300 LOCUST_SPAWN_RATE=30
kubectl -n techx-tf3 rollout restart deploy/load-generator

# Quan sát signal gãy: p99 > 1000ms HOẶC error rate > 1%
# Grafana: dashboard slo-dashboard / apm-dashboard

# Ghi lại:
# - RPS tại điểm gãy (từ Grafana hoặc Locust stats)
# - Service bão hoà sớm nhất (kubectl top pod --sort-by=cpu)
# - pod count tại điểm gãy (kubectl get hpa)
```

**Điền vào bảng (trước tuning):**
| Metric | Giá trị |
|---|---|
| Breakpoint user count | _(điền)_ |
| RPS tại breakpoint | _(điền)_ |
| Service bão hoà đầu tiên | _(điền)_ |
| p99 tại breakpoint | _(điền)_ |
| requests/node tại breakpoint | _(điền)_ |

### Bước 2 — Deploy thay đổi

```bash
# ArgoCD sync sẽ tự pick up:
# - gitops/infrastructure/hpa-hotpath.yaml (HPA tuning)
# Cần build + push image mới cho envoy.tmpl.yaml:
# - phase3 - information/techx-corp-platform/src/frontend-proxy/envoy.tmpl.yaml
# (trigger CI build-push-ecr.yml cho frontend-proxy, sau đó cập nhật imageOverride)
```

### Bước 3 — Verify HPA tuning

```bash
# Xác nhận target đã đổi
kubectl -n techx-tf3 get hpa -o custom-columns=\
  NAME:.metadata.name,\
  TARGET:.spec.metrics[0].resource.target.averageUtilization,\
  MAX:.spec.maxReplicas

# Kết quả mong đợi:
# frontend-proxy-hpa    75    8
# frontend-hpa          75   12
# product-catalog-hpa   75   10
# cart-hpa              65    6
# checkout-hpa          65    8
```

### Bước 4 — Retest breakpoint sau tuning (Phase 2b)

```bash
# Chạy lại ramp tương tự Bước 1, đo breakpoint mới
# Ghi lại requests-per-node: = total RPS / số node thực tế
```

**Điền vào bảng (sau tuning):**
| Metric | Trước tuning | Sau tuning | Δ |
|---|---|---|---|
| RPS đỉnh giữ SLO | _(Bước 1)_ | _(Bước 4)_ | _(tính)_ |
| requests/node | _(Bước 1)_ | _(Bước 4)_ | _(tính)_ |
| Node count | _(không đổi)_ | _(không đổi)_ | 0 |

### Bước 5 — Verify Envoy local_ratelimit

```bash
# Sau khi frontend-proxy image mới được deploy:

# a) Kiểm tra filter đã load
kubectl -n techx-tf3 exec deploy/frontend-proxy -c frontend-proxy -- \
  wget -qO- localhost:${ENVOY_ADMIN_PORT}/stats | grep -E "rate_limit|ratelimit"
# → phải thấy counter: http.ingress_http.local_rate_limiter.*

# b) Test browse bị 429 khi vượt 150 RPS
# (dùng hey hoặc Locust headless mode với >150 RPS browse-only)
# → response phải có: HTTP 429 + header x-local-rate-limit: true

# c) Test checkout KHÔNG bị 429
curl -X POST https://<storefront>/api/checkout -d '{"user_id":"...","...":"..."}'
# → phải 200, KHÔNG phải 429
```

### Bước 6 — Demo xuống mềm (Phase 3 Demo — nộp cho mentor)

```bash
# Đẩy tải lên > breakpoint × 1.5 user
kubectl -n techx-tf3 set env deploy/load-generator \
  LOCUST_USERS=<breakpoint_users * 1.5> LOCUST_SPAWN_RATE=30
kubectl -n techx-tf3 rollout restart deploy/load-generator

# Quan sát Grafana:
# - Browse error rate: phải thấy 429 tăng (shedding hoạt động)
# - Checkout success rate: phải vẫn ≥ 99% (checkout được bảo vệ)
# - Hệ không sập toàn bộ (vẫn có request được phục vụ)

# Screenshot/record Grafana → lưu vào docs/postmortem/ hoặc docs/evidence/
```

---

## Điều chỉnh ngưỡng rate limit sau breakpoint test

Sau khi có breakpoint thật (Bước 1), cập nhật `max_tokens` trong `envoy.tmpl.yaml`:

```yaml
# Công thức: max_tokens ≈ 0.70 × breakpoint_RPS
# Ví dụ: nếu breakpoint là 200 RPS thì max_tokens = 140
token_bucket:
  max_tokens: <0.70 × breakpoint_RPS>
  tokens_per_fill: <0.70 × breakpoint_RPS>
  fill_interval: 1s
```

Cập nhật ADR 0011 với số liệu thật sau khi test.

---

> [!IMPORTANT]
> **Thứ tự image deploy cho envoy.tmpl.yaml:** Vì envoy.tmpl.yaml thay đổi nằm trong source code frontend-proxy, cần:
> 1. Push commit lên branch feat/mandate-19
> 2. Trigger CI workflow build-push-ecr.yml cho `frontend-proxy`
> 3. Cập nhật `imageOverride` trong `values-prod.yaml` với tag mới (pattern: `<tag>-frontend-proxy`)
> 4. Merge PR → ArgoCD sync → frontend-proxy pod rolling restart

> [!NOTE]
> HPA tuning (`hpa-hotpath.yaml`) deploy độc lập qua ArgoCD không cần build image — có thể apply ngay.
