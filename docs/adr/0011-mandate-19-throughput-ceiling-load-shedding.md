# ADR 0011 — Mandate-19: Throughput Ceiling & Load Shedding

**Status:** Accepted
**Date:** 2026-07-23
**Author:** CDO-01 (TF3)
**Mandate:** Directive #19 — Biết trần của mình và nâng trần bằng hiệu suất

---

## Bối cảnh

Directive #19 yêu cầu xác định trần thông lượng thật của hệ, nâng trần bằng hiệu suất (không bằng node), xử nút thắt thông lượng, và đảm bảo hệ xuống mềm (graceful degradation) khi vượt trần bằng cách ưu tiên checkout và shed load browse.

Mandate-02 đã test 200 user thành công với SLO giữ (p95 ~46ms, checkout 99.98%), nhưng **chưa bao giờ chạm breakpoint thật** — 200 user còn rất xa trần. Mandate-16 đã song song hoá checkout critical path, giảm latency từ 185ms xuống ~45ms.

---

## Quyết định

### 1. Trần cũ / mới

| Metric | Trước tuning (breakpoint) | Sau tuning (breakpoint mới) |
|---|---|---|
| RPS đỉnh giữ SLO | _(đo Phase 1 — điền sau)_ | _(đo Phase 2b — điền sau)_ |
| Concurrent user | _(đo Phase 1)_ | _(đo Phase 2b)_ |
| requests/node | _(đo Phase 1)_ | _(đo Phase 2b)_ |
| p99 tại breakpoint | _(đo Phase 1)_ | _(đo Phase 2b)_ |

> Số liệu thực tế được điền sau khi chạy Locust breakpoint test và có evidence Grafana/Prometheus.

### 2. Nút thắt thông lượng đã tìm và nới

**Nút thắt 1 — HPA scale-out threshold quá thấp (65% CPU)**

- **Mô tả:** HPA target 65% CPU → mỗi pod chỉ cần đạt 65m CPU trung bình là đã trigger thêm pod mới. Với CPU request 100m/pod, pod chỉ cần chạy ở 65% công suất là scale — lãng phí node slot, giảm requests-per-node density.
- **Loại bão hoà:** Không phải bão hoà theo nghĩa CPU/mem cạn, mà là **scale-out quá sớm** → không tận dụng hết capacity của pod đang chạy.
- **Cách nới:**
  - `frontend-proxy-hpa`: `averageUtilization 65% → 75%`
  - `frontend-hpa`: `averageUtilization 65% → 75%`, `maxReplicas 8 → 12`
  - `product-catalog-hpa`: `averageUtilization 65% → 75%`, `maxReplicas 8 → 10`
  - `cart-hpa`, `checkout-hpa`: **giữ 65%** — revenue-critical, ưu tiên latency
- **File:** [`gitops/infrastructure/hpa-hotpath.yaml`](file:///d:/Phase3_01/Phase3-TF3-Infra-Sentinel/gitops/infrastructure/hpa-hotpath.yaml)

**Nút thắt 2 — Envoy circuit breaker `max_requests` mặc định (1024)**

- **Mô tả:** Envoy default `max_requests=1024` cho cluster `frontend`. Khi throughput cao, Envoy có thể reject request ở tầng proxy trước khi backend thực sự quá tải — gây error không phản ánh đúng capacity backend.
- **Loại bão hoà:** Connection/queue depth (Envoy pending requests ceiling).
- **Cách nới:** `max_requests: 1024 → 4096` trong `circuit_breakers.thresholds` của cluster `frontend`.
- **File:** [`phase3 - information/techx-corp-platform/src/frontend-proxy/envoy.tmpl.yaml`](file:///d:/Phase3_01/Phase3-TF3-Infra-Sentinel/phase3%20-%20information/techx-corp-platform/src/frontend-proxy/envoy.tmpl.yaml)

### 3. Cơ chế load shedding — xuống mềm khi vượt trần

**Lựa chọn:** Envoy `envoy.filters.http.local_ratelimit` (in-process token bucket)

**Lý do chọn local_ratelimit:**
- Chạy in-process trong Envoy → không cần Redis external, không thêm dependency, không tăng latency đáng kể
- Per-route override → có thể cấu hình khác nhau cho checkout vs browse trên cùng một filter chain
- Phản ứng tức thì (không cần round-trip đến rate limit server)
- Trả HTTP 429 với header `x-local-rate-limit: true` → client và observability có thể phân biệt

**Cấu hình:**

| Route | Token bucket | Hành vi khi vượt |
|---|---|---|
| `/api/checkout` (`checkout_protected`) | Dùng global bucket: 10 000 token/s | **Không bao giờ bị shed** (10k >> thực tế) |
| `/` catch-all (`browse_shedable`) | `max_tokens=150, fill=150/s` | HTTP 429 + `x-local-rate-limit: true` |

**Tại sao 150 RPS cho browse:**
- Mandate-02: frontend ~1.4 RPS baseline, product-catalog ~1.1 RPS baseline, nhưng đây là traffic demo — breakpoint thật chưa được đo
- 150 RPS được ước tính là ~75% breakpoint dự kiến (~200 RPS) dựa trên capacity analysis (7 node, 8 pod frontend max)
- Ngưỡng này **sẽ được điều chỉnh** sau Phase 1 breakpoint test: nếu breakpoint là X RPS thì set `max_tokens ≈ 0.70 × X`

**Thứ tự route (quan trọng):**
```
/otlp-http/ → collector
/images/    → image-provider
/flagservice/ → flagd (không đụng, Directive #1)
/api/checkout → frontend [PROTECTED — không shed]
/           → frontend [SHEDABLE — token bucket 150/s]
```

### 4. Nâng trần bằng gì (không thêm node)

| Kỹ thuật | Tác động |
|---|---|
| HPA CPU target 65% → 75% (browse services) | Mỗi pod gánh nhiều request hơn trước khi scale → requests-per-node density tăng |
| `maxReplicas` nới (frontend 8→12, product-catalog 8→10) | HPA có thể burst cao hơn ngưỡng cũ khi cần — chứng minh trần mới |
| Envoy `circuit_breakers.max_requests` 1024→4096 | Loại bỏ Envoy-level bottleneck trước khi backend thực sự cạn |
| Envoy `local_ratelimit` shed browse khi vượt trần | Giữ checkout throughput ổn định dù tổng traffic vượt trần |

---

## Trade-offs đã chấp nhận

| Trade-off | Lý do chấp nhận |
|---|---|
| Browse pod chạy ở CPU cao hơn (75% target vs 65%) trước khi scale | Browse không phải revenue-critical; latency browse tăng nhẹ chấp nhận được để tăng density |
| Browse user bị HTTP 429 khi vượt trần | Mandate yêu cầu shed load thay vì sập toàn bộ; checkout vẫn được bảo vệ |
| Token bucket 150 RPS là placeholder — chưa có số thật | Sẽ được điều chỉnh sau Phase 1 breakpoint test; hiện tại chọn số bảo thủ để tránh shed quá sớm |
| maxReplicas tăng có thể tăng resource quota usage | Đã có ResourceQuota `pods: 100` (sau Mandate-02 nâng từ 50) — có đủ headroom |

---

## Không thay đổi

- Karpenter NodePool — không thêm node
- `checkout-hpa` và `cart-hpa` — giữ 65% CPU target
- flagd, `/flagservice/` route, `/otlp-http/` route
- Stateful services (postgres/kafka/valkey/RDS/ElastiCache/MSK)
- Topology prod (PDB, topologySpreadConstraints, graceful shutdown)
- `imageOverride` của bất kỳ service nào — không có code change

---

## Verification

```bash
# 1. Xác nhận HPA target mới
kubectl -n techx-tf3 get hpa -o custom-columns=\
  NAME:.metadata.name,TARGET:.spec.metrics[0].resource.target.averageUtilization,MIN:.spec.minReplicas,MAX:.spec.maxReplicas

# 2. Xác nhận Envoy local_ratelimit filter đã load
kubectl -n techx-tf3 exec deploy/frontend-proxy -c frontend-proxy -- \
  wget -qO- localhost:${ENVOY_ADMIN_PORT}/stats | grep rate_limit

# 3. Test shedding thủ công — gửi >150 req/s browse, xác nhận 429
# (xem docs/mandate-19-implement-plan.md Phase 3 Demo)

# 4. Kiểm tra checkout KHÔNG bị 429 song song
curl -X POST https://<storefront>/api/checkout -d '...'  # phải 200, không phải 429
```

---

## Tham chiếu

- [ADR 0004 — Mandate-02 flash sale](file:///d:/Phase3_01/Phase3-TF3-Infra-Sentinel/docs/adr/0004-mandate-02-flash-sale-cdo02.md)
- [Mandate-02 load test report](file:///d:/Phase3_01/Phase3-TF3-Infra-Sentinel/docs/mandate-02-load-test-report.md)
- [Mandate-16 checkout latency optimization](file:///d:/Phase3_01/Phase3-TF3-Infra-Sentinel/docs/mandate-16-checkout-latency-optimization.md)
- [hpa-hotpath.yaml](file:///d:/Phase3_01/Phase3-TF3-Infra-Sentinel/gitops/infrastructure/hpa-hotpath.yaml)
- [envoy.tmpl.yaml](file:///d:/Phase3_01/Phase3-TF3-Infra-Sentinel/phase3%20-%20information/techx-corp-platform/src/frontend-proxy/envoy.tmpl.yaml)
