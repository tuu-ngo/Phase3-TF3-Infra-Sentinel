# PM-154 — Mandate #19: Calibrated Graceful Degradation / Load Shedding

| Field | Value |
|---|---|
| Jira | PM-154, thuộc PM-151 — Mandate #19 Throughput Ceiling |
| Owner | Long Trần |
| Dependency | PM-153 approved `new_ceiling`; PM-155 rehearsal and ADR |
| Runtime target | `phase3 - information/techx-corp-platform/src/frontend-proxy/envoy.tmpl.yaml` |
| Document state | `EXECUTION PLAN`; không phải deployed config, live 429 evidence hoặc PM-154 Done |

## 1. Mục tiêu và boundary

Khi offered load vượt `new_ceiling`, PM-154 phải shed tải không thiết yếu có chủ đích để bảo vệ checkout, giữ hệ thống phục hồi được và phân biệt được `429` dự kiến với `5xx/timeout` ngoài ý muốn.

Không chốt `100`, `150`, `200 RPS` trước benchmark. Rate-limit calibration chỉ bắt đầu sau PM-153 bàn giao new ceiling, checkout load đo được và node/proxy baseline.

## 2. Protected journey và shed-first classification

Chỉ bảo vệ `/api/checkout` là chưa đủ vì checkout có dependency. Canonical overload profile phải chuẩn bị/seed cart trước stage overload và giữ protected write path:

| Class | Route/operation | Policy |
|---|---|---|
| `protected_cart_write` | `POST /api/cart` | quota riêng; không dùng browse bucket |
| `protected_checkout` | `POST /api/checkout` | quota emergency riêng; không bị browse bucket |
| Checkout dependency | exact dependency đã chứng minh bằng trace/contract | thêm vào protected class hoặc pre-seed trước overload |
| `shed_browse` | homepage, product browse/search không thiết yếu, recommendations, reviews, ads | local token bucket; 429 có chủ đích |
| Images/flag/readiness | `/images/`, `/flagservice/`, health/ops paths | policy riêng; không áp browse bucket mù quáng |

`GET /api/products/<id>` không được đồng thời coi là browse và checkout dependency mà không có profile phân tách. Canonical lựa chọn là: pre-seed product/cart trước overload, sau đó protected stream gửi `POST /api/cart`/`POST /api/checkout`; nếu end-to-end test bắt buộc product lookup, phải route/metric riêng và chứng minh nó không bị `shed_browse`.

Route ordering phải đặt các route protected trước catch-all `/`. Đặt tên route rõ để access log `%ROUTE_NAME%` có giá trị:

```text
protected_checkout
protected_cart_write
shed_browse
images
flagservice
```

## 3. Calibration formula

Inputs chỉ được lấy từ PM-153/PM-155 evidence:

```text
checkout_rps_at_new_ceiling = measured protected checkout RPS
safety_factor = 1.25 (hoặc giá trị PM/mentor duyệt và record trước run)
operational_margin = 10% of new_ceiling (hoặc giá trị được duyệt)

reserved_checkout = checkout_rps_at_new_ceiling * safety_factor
safe_browse_cap = max(
  0,
  new_ceiling - reserved_checkout - operational_margin
)
minimum_ready_proxy_replicas = min Ready replicas observed during rehearsal
per_proxy_browse_cap = floor(safe_browse_cap / minimum_ready_proxy_replicas)
checkout_emergency_cap = checkout_rps_at_new_ceiling * 1.10
```

Lưu inputs, units, rounding, minimum Ready replicas và resulting buckets trong evidence. Nếu `safe_browse_cap <= 0`, không hạ checkout quota để làm số đẹp; trả `BLOCKED_CAPACITY_MODEL` và escalates PM-153/PM-155.

## 4. Envoy design contract

### 4.1 Local rate-limit trade-off

Envoy HTTP Local Rate Limit token bucket mặc định là **per Envoy process**, không global cluster quota. Với `frontend-proxy` HPA hiện có `minReplicas=2`, `maxReplicas=8`, effective cluster cap xấp xỉ:

```text
per-proxy bucket * number of Ready frontend-proxy replicas
```

ADR phải ghi trade-off. Deadline path chọn một trong các phương án và ghi rõ:

1. giữ `frontend-proxy` replicas cố định trong overload demo; hoặc
2. tính cap theo minimum Ready replicas và lưu effective cap ở từng thời điểm; hoặc
3. dùng global rate-limit service nếu yêu cầu quota cluster thật.

Không tuyên bố Local Rate Limit là global limit. Node-set và proxy replica count là evidence bắt buộc.

### 4.2 Explicit filter state

Implementation phải cấu hình rõ, không dựa vào runtime defaults:

```yaml
http_filters:
  - name: envoy.filters.http.local_ratelimit
    typed_config:
      stat_prefix: mandate19_shed
      filter_enabled:
        default_value: { numerator: 100, denominator: HUNDRED }
      filter_enforced:
        default_value: { numerator: 100, denominator: HUNDRED }
      response_headers_to_add:
        - append_action: OVERWRITE_IF_EXISTS_OR_ADD
          header:
            key: x-techx-load-shed
            value: browse
  - name: envoy.filters.http.router
```

Shadow rehearsal có thể dùng `filter_enabled=100%`, `filter_enforced=0%`; final overload demo chỉ pass khi `filter_enabled=100%` và `filter_enforced=100%`, response `429`, `x-techx-load-shed: browse` và `x-envoy-ratelimited: true` được quan sát. Filter phải đứng trước router.

### 4.3 Metrics and admin safety

Dashboard/query phải capture local-rate-limit counters theo route/stat prefix: `enabled`, `ok`, `rate_limited`, `enforced`, 429 rate, offered/served RPS và upstream errors. `429` có chủ đích không được gộp vào unexpected failure.

Current Envoy admin listener bind `0.0.0.0`. Trước khi scrape admin metrics, restrict bằng listener/service exposure và NetworkPolicy chỉ cho Prometheus/approved operator path; không public admin port để phục vụ demo. Nếu chưa chứng minh được restriction, PM-154 là `BLOCKED_ADMIN_EXPOSURE`.

## 5. Implementation sequence

1. Capture current Envoy routes, HPA Ready replica floor, admin exposure, image/config SHA và node-set hash.
2. Add named route classification and filter in a reviewed implementation PR; do not combine unrelated HPA/datastore changes.
3. Run shadow mode (`enabled=100`, `enforced=0`) to validate route matching, counters and headers without rejection.
4. Calibrate formula using PM-153 new-ceiling evidence; record exact bucket/fill values and per-proxy effective cap.
5. Promote final enforcement only after shadow query/trace shows checkout journey does not traverse browse bucket.
6. Apply final policy through CI/GitOps, wait for all proxy replicas Ready, then run overload rehearsal with same node-set freeze.

## 6. Verification protocol

### Preflight

- PM-153 `new_ceiling` and checkout RPS evidence present.
- Protected checkout stream is distinct from shed browse stream.
- Node-set hash unchanged; proxy Ready replicas and HPA state recorded.
- Envoy config validates; route names and filter stats exist.
- Prometheus access to Envoy metrics is allowed without exposing admin publicly.

### Overload stage

1. Hold protected checkout stream at measured checkout RPS.
2. Offer browse load above calibrated `safe_browse_cap` for a sustained stage of at least 5 minutes.
3. Observe intentional browse `429` with route/header/counter evidence.
4. Confirm `POST /api/cart` and `POST /api/checkout` are not rejected by browse bucket; checkout has its own emergency cap.
5. Confirm checkout success `>=99%`, checkout p99 within approved budget, no unexpected 5xx/timeout/OOM/restart and no node/proxy replacement.
6. Lower offered load; confirm 429 rate returns to zero/normal and checkout/browse recover.

Required source of truth: Locust CSV, exact-window Prometheus range query, Envoy stats/access logs, trace IDs and node/proxy timeline. Grafana screenshot is presentation only.

## 7. Rollback and stop conditions

Rollback to the last known-good GitOps revision when:

- protected cart/checkout receives browse 429 or unexpected 5xx/timeout;
- checkout success/p99 violates budget;
- filter enabled/enforced counters do not match configured state;
- admin metrics are publicly reachable;
- proxy replicas scale and effective cap is not recalculated;
- node set changes, OOM/restart occurs, or recovery fails;
- 429 is caused by route mismatch rather than intentional shed policy.

Rollback must preserve evidence of the rejected run. Do not increase bucket until root cause and formula inputs are reviewed; do not remove all rate limiting to make the demo green.

## 8. Evidence and DoD

```text
docs/evidence/mandate-19/pm-154/
  route-classification.yaml
  calibration-inputs.json
  envoy-config-rendered.yaml
  shadow/{locust.csv,prometheus.json,envoy-stats.json}
  enforced/{locust.csv,prometheus.json,envoy-stats.json,trace-ids.json}
  rollback.log
  node-proxy-timeline.jsonl
  closure-checklist.md
```

PM-154 chỉ `Done` khi:

- Jira owner/dependency/DoD được ghi rõ và file không có local Windows URI;
- protected cart/checkout journey được định nghĩa, test profile không bị browse bucket chặn;
- bucket được tính từ PM-153 new ceiling, không có ngưỡng đoán trước;
- per-proxy Local Rate Limit caveat và replica floor được evidence;
- filter state `enabled=100%`, `enforced=100%` được xác minh live;
- route names, 429 status/header và enabled/ok/rate_limited/enforced counters có raw evidence;
- browse 429 có chủ đích trong sustained overload, checkout success/p99 giữ SLO;
- no unexpected 5xx/timeout/OOM/restart/node change và recovery pass;
- admin port không public; rollback được rehearsal;
- sanitized evidence đã commit để PM-155 dùng trong demo/ADR.

Tài liệu này vẫn là implementation contract. Không kết luận Mandate #19 pass nếu chưa có deployed config và runtime evidence.
