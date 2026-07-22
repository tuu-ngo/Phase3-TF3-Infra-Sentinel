# PM-153 — Mandate #19: Bottleneck Tuning and New-Ceiling Plan

| Field | Value |
|---|---|
| Jira | PM-153, thuộc PM-151 — Mandate #19 Throughput Ceiling |
| Owner | Hoàng Công Trí Dũng |
| Dependency | PM-152 approved old ceiling; PM-155 canonical protocol/freeze |
| Scope | Tuning một bottleneck chính trên cùng node set; không mua throughput bằng node |
| Document state | `EXECUTION PLAN`; không phải runtime evidence hoặc kết luận PM-153 Done |

## 1. Mục tiêu và nguyên tắc

PM-153 chỉ được nới bottleneck đã được PM-152 chứng minh bằng saturation metric và trace. Mục tiêu là `new_ceiling > old_ceiling` và `RPS/node` tăng trong cùng traffic protocol, SLO, node set và correctness gates.

Không chọn trước `product-catalog`, HPA hay DB pool. PM-152 phải xác định bottleneck bão hòa sớm nhất; co-bottleneck được ghi nhận nhưng không được cherry-pick một candidate thuận tiện làm root cause.

Mỗi iteration là một thí nghiệm độc lập:

```text
one hypothesis
  -> one narrowly related change group
  -> same canonical PM-152 stage protocol
  -> saturation metric + trace before/after
  -> correctness and SLO validation
  -> retain or rollback
```

Không đổi đồng thời HPA max, DB pool, HPA behavior và keep-alive rồi gọi toàn bộ RPS tăng là do một tuning.

## 2. Input contract từ PM-152

PM-153 không bắt đầu nếu thiếu:

- old ceiling là sustained **served RPS** và highest passing stage đã re-run;
- offered/served RPS, exact traffic mix, stage duration và SLO/p99 budgets;
- node-set hash, node name/UID/providerID/instance type/AZ và load-generator location;
- primary bottleneck, co-bottlenecks, saturation metric và trace IDs;
- baseline replicas/HPA, CPU/throttling/memory/GC, DB/queue/cache signals;
- correctness result và Git/image/config revisions.

Nếu PM-152 `BLOCKED`, `INCONCLUSIVE` hoặc node-set hash thiếu, PM-153 trả `BLOCKED_INPUT`.

## 3. Candidate decision matrix

| Candidate | Evidence cần có trước thay đổi | Change boundary | Keep/rollback gate |
|---|---|---|---|
| HPA replica ceiling | HPA current/max, Pending pods, node CPU/memory headroom, no Karpenter NodeClaim | Một HPA target hoặc max policy trong một iteration | Pod schedule trên node set; no Pending; requests fit; RPS/node tăng |
| HPA response behavior | scale-up delay và ready timeline chứng minh lag, không phải CPU saturation khác | Chỉ `behavior`/target của workload được chọn | Ready time giảm; no oscillation/throttle; same node hash |
| DB pool | pool wait/open/in-use + PostgreSQL active/max connections và trace | Chỉ pool của service được chứng minh nghẽn | `pool_per_pod * max_replicas + other services + reserve < max_connections` |
| Keep-alive/reuse | connection churn/handshake và trace | Một client/upstream transport setting | p99/CPU/connection churn cải thiện, không tăng error |
| Service/resource code | profile/trace chỉ ra một hàm/path nóng | One code-path change | Functional/correctness tests + same image provenance |
| Queue/cache/datastore | lag/wait/eviction/error signal | Một policy/config group liên quan | lag/wait giảm, no loss/duplicate event |

## 4. HPA and node-set guardrails

Repo hiện có nhiều HPA ceilings (frontend-proxy/frontend/product-catalog/checkout tới `8`, cart/product-reviews tới `6`, recommendation/ad tới `4`). Đây là baseline cần kiểm live, không phải quyền tự tăng một loạt workload.

Nếu hypothesis là HPA ceiling:

1. Tăng **một** workload ceiling trong một iteration, với giá trị được tính từ allocatable CPU/memory của exact node set; không dùng ví dụ `12/16` khi chưa có capacity arithmetic.
2. Chứng minh pod mới schedule được trên node set hiện tại; không có Pending pod, CPU/memory requests vẫn fit, topology/AZ không đổi.
3. Freeze Karpenter scale-up và voluntary disruption bằng change đã review; NodePool/NodeClaim mới hoặc node replacement làm run invalid.
4. Ghi `desired/current/max`, Ready replicas, Pending duration, requests/limits và RPS/node.
5. Không nới HPA để che một DB/queue bottleneck.

HPA behavior tuning cũng chỉ đổi một behavior/target group mỗi iteration. Theo dõi scale-up latency, oscillation, throttling và readiness; không gộp maxReplicas với behavior trong cùng thí nghiệm trừ khi owner tuyên bố đó là một hypothesis duy nhất và có rollback riêng.

## 5. Connection-pool arithmetic

`product-catalog` hiện có `SetMaxOpenConns(20)`, `SetMaxIdleConns(10)` và `SetConnMaxLifetime(5m)`. Số `20` là baseline evidence, không phải bằng chứng pool là bottleneck và `50` không phải giá trị mặc định được phép áp dụng.

Trước khi đổi pool, tính và lưu:

```text
total_reserved_connections =
  (pool_per_pod * max_replicas_of_service)
  + product-reviews reservation
  + accounting reservation
  + migrations/health/ops reserve

require total_reserved_connections < PostgreSQL max_connections
```

Chừa reserve được owner phê duyệt; không chỉ so với pool hiện tại. Capture `pg_stat_activity`, max_connections, pool `Open/InUse/WaitCount/WaitDuration`, service replicas và trace. Nếu PostgreSQL shared capacity không đủ, rollback pool increase hoặc redesign workload; không chuyển sự cố từ product-catalog sang RDS.

## 6. Test protocol cho từng iteration

### Before

- Re-run exact PM-152 highest-passing stage và baseline saturation query.
- Verify `BASE_SHA`, image digests, config revision, traffic profile SHA và node-set hash.
- Confirm PM-155 freeze: không deploy PM-144/148/129, Envoy, HPA ngoài candidate, datastore, flagd, backup/restore hoặc observability.

### Change

- Commit một thay đổi hẹp; ghi hypothesis, expected signal, resource/cost risk, owner và rollback commit.
- Terraform/GitOps plan phải show intended resources only; no accidental RDS/datastore replacement.
- Apply through normal CI/Argo path; record rollout and Ready time.

### Re-test

- Dùng cùng Locust profile, traffic mix, R0/stage schedule, duration, source endpoint và node set.
- Chạy đủ highest-passing stage và stage kế tiếp; không dừng sớm ở một spike.
- Lưu exact-window Prometheus, Locust CSV, HPA/node timeline, trace và logs.

### Decision

Giữ change chỉ khi tất cả điều kiện sau pass: `new_ceiling > old_ceiling`, `RPS/node` tăng, primary saturation giảm/cải thiện, SLO/p99 giữ, no OOM/restart/Pending/node replacement, correctness pass và no unexpected 5xx/timeout. Nếu không, rollback về commit trước và ghi negative result; không chọn cherry-pick run tốt nhất.

## 7. Correctness gate

Throughput tăng nhưng dữ liệu sai là failure. Với mỗi run, reconcile theo correlation/order ID:

```text
successful checkout requests
  == unique orders created
  == expected successful payment events
  == expected Kafka orders/events consumed

duplicate order = 0
duplicate payment = 0
lost/missing expected event = 0
cart/total/inventory invariant = PASS
```

Tách rõ `429` có chủ đích của PM-154 (chưa áp dụng trong PM-153) khỏi `5xx`, timeout, downstream failure và validation error. Mọi correctness mismatch trả `FAILED_CORRECTNESS`, dù RPS cao hơn.

## 8. Evidence và DoD

```text
docs/evidence/mandate-19/pm-153/
  baseline-from-pm-152.json
  iterations/<n>/{hypothesis,plan,metrics,traces,locust.csv,correctness.json}
  tuning-decision-log.md
  new-ceiling-summary.json
  rollback-proof.txt
```

PM-153 chỉ `Done` khi:

- primary bottleneck có metric + trace và candidate matrix không bị bỏ qua;
- mỗi iteration có đúng một hypothesis/change group và same protocol;
- plan/diff không thêm node hoặc thay đổi topology;
- HPA tuning chứng minh pod schedule trên exact node set, không Pending/NodeClaim mới;
- DB pool tuning có connection arithmetic và operational reserve;
- new ceiling và RPS/node tăng so với PM-152;
- saturation metric cải thiện, p99/SLO không giảm;
- correctness reconciliation pass, không duplicate/lost event;
- rollback path đã được kiểm chứng hoặc negative result được lưu;
- raw Locust/Prometheus/trace/HPA/node evidence đủ cho PM-155.

Nếu `new_ceiling <= old_ceiling`, PM-153 chưa đạt và PM-155 vẫn `BLOCKED`; không đổi SLO hoặc gọi “ổn định” dựa trên một metric đơn lẻ.
