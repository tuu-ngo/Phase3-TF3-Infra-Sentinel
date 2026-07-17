# Mandate 02 — CDO-02 Load Test Report: Reliability & Cost Optimization

**Trạng thái tài liệu:** Hoàn tất  
**Ngày chạy:** 15/07/2026

## 0. Executive summary

Tài liệu trình bày kết quả đánh giá Mandate 02 của CDO-02 cho hai trụ cột Reliability và Cost Optimization, gồm capacity, autoscaling, SLO, node utilization và chi phí trong cửa sổ 200 users.

Một lần test đạt không chỉ dựa trên Locust `0 fail`. Kết luận phải đồng thời chứng minh:

- CDO-01 thực sự đạt 200 users trong test window.
- HPA scale từ baseline 16 lên peak 22 và co về 16.
- SLO đạt khi peak, không có OOM/restart/Pending/disruption che khuất kết quả.
- Node inventory và cost/hour không tăng ngoài điều kiện được giải thích.
- Successful order được đối chiếu giữa Locust và Prometheus/Grafana.
- Protection tạm thời của Karpenter đã cleanup.

## 0.1 Quy tắc lập báo cáo

- Mọi claim định lượng phải trỏ tới evidence ID.
- Dùng timestamp có timezone `UTC+07:00`.
- Phân biệt baseline, ramp, peak, cooldown và cleanup.
- Không dùng ảnh hoặc số liệu của lần chạy trước.
- Không đổi query window giữa SLO và order reconciliation.
- Chỉ trình bày số liệu có evidence hoặc phép tính suy ra trực tiếp.

## 0.2 Test phase definition

| Phase | Định nghĩa | Evidence chính |
|---|---|---|
| Before | 5–10 phút trước T0, tải nền ổn định | HPA=16, node, restart baseline, SLO baseline |
| Ramp | T0 đến khi đạt 200 users | HPA transition, Pending/events |
| Peak | 200 users ổn định trong cửa sổ chính thức | HPA=22, SLO, OOM/5xx, node |
| Cooldown | Sau khi CDO-01 dừng tải | HPA scale-down, pod health |
| Cleanup | Sau cooldown | NodePool/annotation/GitOps health |

## 1. Test metadata

| Trường | Giá trị |
|---|---|
| Test ID | Mandate-02-20260715-1245 |
| Namespace | `techx-tf3` |
| Concurrent users | 200 |
| TEST_START | 15/07/2026 12:45 UTC+7 |
| TEST_END | 15/07/2026 13:02 UTC+7 |
| Timezone | Asia/Bangkok (UTC+07:00) |
| Duration | 17 phút |
| CDO-01 artifact | Locust screenshot/statistics; checkout 2399 request/0 fail, cart 10700 request/0 fail |
| CDO-02 evidence location | `docs/postmortem/Mandate02-image/` |

### 1.1 Test contract validation

| Check | Kết quả | Evidence |
|---|---|---|
| Peak users | 200 | Locust/HPA peak evidence |
| Official window | 12:45–13:02 UTC+7 | Prometheus query và cost window |
| Test duration | 17 phút | TEST_START/TEST_END |
| Test completion | Hoàn tất, không abort | Báo cáo CDO-01 |

## 2. Reliability

### 2.1 Monitoring timeline

| Phase | HPA-managed pod | Node | Trạng thái |
|---|---:|---:|---|
| Before | 16 | 7 | Baseline |
| Peak | 22 | 7 | 200 users; frontend 2→7, product-reviews 2→3 |
| After | 16 | 7 | Về baseline khoảng 10 phút sau dừng tải |

Scale-up tập trung ở `frontend` (2→7) và `product-reviews` (2→3). Các HPA khác giữ baseline. Sau khi tải dừng lúc 13:02, tổng HPA-managed pod trở về 16 trong khoảng 10 phút. Node count giữ nguyên 7 tại cả ba mốc.

Snapshot commands:

```powershell
$NS='techx-tf3'
Get-Date -Format o
kubectl -n $NS get hpa
kubectl -n $NS get pods -o wide
kubectl -n $NS top pods --containers
kubectl -n $NS get resourcequota
kubectl -n $NS get events --sort-by=.lastTimestamp
kubectl get nodes -o wide
kubectl get nodeclaims -o wide
kubectl top nodes
```

Tổng HPA replica:

```powershell
$replicas=kubectl -n $NS get hpa -o jsonpath='{range .items[*]}{.status.currentReplicas}{"\n"}{end}'
($replicas | ForEach-Object {[int]$_} | Measure-Object -Sum).Sum
```

### 2.2 Stability results

| Signal | Result | Threshold | PASS/FAIL | Evidence |
|---|---:|---:|---|---|
| OOMKilled mới | 0 trong lần test chính thức | 0 | PASS | Kết quả report: không phát sinh sự cố mới |
| Restart do tải | 0 ảnh hưởng tải | 0 | PASS | Không có crash/restart được báo cáo |
| Pending >2 phút | 0 | 0 | PASS | HPA đạt 22, không bị quota chặn |
| FailedScheduling/quota | 0 | 0 | PASS | Quota 100 và pod scale thành công |
| Karpenter critical eviction | 0 | 0 | PASS | Guardrail giữ workload ổn định |
| CPU throttling ảnh hưởng SLO | Không quan sát thấy ảnh hưởng | Không | PASS | p95 giữ 46–48ms |
| Memory >85% limit kéo dài | Không có OOM trong official run | Không gây OOM | PASS | Resource remediation có hiệu lực |

#### Incident/event timeline

| Timestamp | Signal/Event | Workload | Ảnh hưởng request/SLO | Root cause | Action/Handoff |
|---|---|---|---|---|---|
| Không có | No qualifying incident observed in official test window | N/A | Không ảnh hưởng | N/A | Không cần abort |

Nếu không có incident, ghi rõ `No qualifying incident observed in test window` và trỏ tới event/restart evidence; không để bảng trống.

PromQL throttling:

```promql
sum by (pod) (rate(container_cpu_cfs_throttled_periods_total{namespace="techx-tf3",container!=""}[2m]))
/
sum by (pod) (rate(container_cpu_cfs_periods_total{namespace="techx-tf3",container!=""}[2m]))
```

PromQL restart:

```promql
increase(kube_pod_container_status_restarts_total{namespace="techx-tf3"}[5m])
```

### 2.3 SLO results

| SLO | Locust | Prometheus/Grafana | Threshold | PASS/FAIL |
|---|---:|---:|---:|---|
| Storefront p95 | 46–48ms | 46–48ms trước/trong/sau | `<1s` | PASS |
| Checkout success | 2399 request, 0 fail | 99.9825%; 2327 PlaceOrder, 0 STATUS_CODE_ERROR | `>=99%` | PASS |
| Browse/cart success | 10700 request, 0 fail | 100.0000% | `>=99.5%` | PASS |
| HTTP 5xx | 0 fail được Locust ghi nhận | 0 STATUS_CODE_ERROR cho PlaceOrder | Trong error budget | PASS |

#### SLO interpretation

- Locust đo trải nghiệm client và có thể thấy lỗi trước khi request tới service.
- Prometheus/Grafana đo server/span/infrastructure tùy metric.
- Hai nguồn không bắt buộc bằng tuyệt đối nhưng phải cùng xu hướng và cùng window.
- Nếu Locust có fail nhưng server metric không có 5xx, kiểm tra timeout, connection reset, proxy/circuit breaker và client-side failure.
- Nếu server metric có error nhưng Locust không fail, kiểm tra retry, background traffic và metric scope.

### 2.4 HPA validation

| Timestamp | HPA | CPU current/target | Replica before | Replica after | Event |
|---|---|---|---:|---:|---|
| ~12:44 | All HPA | Idle 1–7%/65% tham chiếu | 16 tổng | 16 tổng | Baseline |
| Peak | frontend | Vượt target trong tải/65% | 2 | 7 | Scale-up |
| Peak | product-reviews | Vượt target trong tải/65% | 2 | 3 | Scale-up |
| ~10 phút sau stop | frontend/product-reviews | Tải giảm | 7/3 | 2/2 | Scale-down |

Acceptance:

- Before tổng HPA pod = 16.
- Peak tổng HPA pod = 22.
- After cooldown tổng HPA pod = 16.
- Không bị quota hoặc scheduling chặn.
- SLO vẫn đạt trong peak.

**Reliability verdict:** `GO`

### 2.5 Reliability narrative

```text
Tại baseline, hệ thống có 16 HPA-managed pod và 7 node.
Khi CDO-01 đạt 200 users, HPA scale lên 22 pod; frontend tăng 2→7 và product-reviews tăng 2→3.
Trong peak, storefront p95 giữ 46–48ms, checkout success 99.9825%, browse/cart success 100%.
Không có OOM, restart, Pending hoặc Karpenter disruption ảnh hưởng lần test chính thức.
Sau khi dừng tải, HPA về 16 trong khoảng 10 phút.
Reliability kết luận GO vì cả ba SLO đạt và autoscaling hoạt động đúng `16→22→16`.
```

## 3. Cost Optimization

### 3.1 Node inventory

| Phase | Instance type | Capacity type | Quantity | Unit price USD/h | Subtotal USD/h | Evidence |
|---|---|---|---:|---:|---:|---|
| Before | t3.large | On-Demand | 3 | $0.1056 | $0.3168 | Node inventory live |
| Before | t3.medium | On-Demand | 1 | $0.0528 | $0.0528 | Node inventory live |
| Before | t3.small | Spot | 3 | ~$0.0116 | $0.0348 | AWS Spot price 3 AZ |
| Peak | Inventory không đổi | 4 On-Demand/3 Spot | 7 | Như before | $0.4044 | HPA/node peak image |
| After | Inventory không đổi | 4 On-Demand/3 Spot | 7 | Như before | $0.4044 | HPA/node after image |

Node identity phải được so sánh, không chỉ node count. Node count bằng nhau nhưng node bị thay thế giữa test vẫn có thể tạo disruption và thay đổi segment cost.

| Node/NodeClaim | Before | Peak | After | Created/terminated trong test | Ghi chú |
|---|---|---|---|---|---|
| 3 NodeClaim Spot `mlxx8`/`mqz5x`/`v5h5j` | Có | Có, cùng identity | Có, cùng identity | Không | Chỉ tăng tuổi; không launch node mới |

### 3.2 Test-window cost

```text
segment_cost = segment_cost_per_hour * segment_duration_seconds / 3600
test_window_cost = sum(segment_cost)
```

| Segment | Start | End | Duration h | Cost/h | Segment cost |
|---|---|---|---:|---:|---:|
| 1 | 12:45 | 13:02 | 0.283333 | $0.4044 | $0.1146 |
| **Total** | | | | | **$0.1146** |

### 3.3 Successful orders và reconciliation

| Nguồn | Checkout total | Failure | Successful | Window/query/artifact |
|---|---:|---:|---:|---|
| Locust | 2399 checkout | 0 | 2399 | Có thể lẫn biên/ramp ngoài official window |
| Prometheus/Grafana | 2327 PlaceOrder | 0 STATUS_CODE_ERROR | 2327 | Đúng 12:45–13:02 UTC+7 |

```text
order_delta_pct = abs(locust_success - prometheus_success) / locust_success * 100
cost_per_order = test_window_cost / accepted_successful_orders
```

Chênh lệch phải được giải thích theo timezone, query boundary, ramp, retry và metric semantics trước khi chọn số order.

| Metric | Baseline | Test | Delta | PASS/FAIL |
|---|---:|---:|---:|---|
| Node count | 7 | 7 | 0 | PASS |
| Cost/hour | $0.4044 | $0.4044 | $0 | PASS |
| Test-window cost | N/A | $0.1146 | N/A | PASS |
| Successful orders | Không có baseline cùng window | 2327 | Không so sánh | Đã xác nhận |
| Cost/order | Không có baseline hợp lệ | ~$0.0000493 | Không so sánh | Đã tính |
| Cost/request, phạm vi checkout+cart được báo cáo | Không có baseline hợp lệ | ~$0.00000875 cho 13,099 request | Không so sánh | Scoped metric |

Không kết luận cost/order “không phình” nếu không có baseline order cùng cửa sổ. Khi thiếu baseline, chỉ kết luận cost/hour, test-window cost và cost/order của lần test.

#### Reconciliation decision

```text
Locust successful checkout: 2399
Prometheus successful checkout: 2327
Absolute delta: 72
Delta percentage: ~3.00% so với Locust
Accepted successful orders: 2327
Selected source: Prometheus PlaceOrder
Selection reason: Truy vấn đúng official window; Locust có thể gồm request ở biên/ramp
```

### 3.4 Scale-down và cleanup

| Action | Owner | Status | Evidence |
|---|---|---|---|
| CDO-01 xác nhận tải dừng | CDO-01 | DONE | Test kết thúc 13:02 |
| HPA về 16 | CDO-02 xác nhận | DONE | Ảnh after, khoảng 10 phút sau stop |
| Node after không cao hơn before | CDO-02 xác nhận | DONE | 7 node không đổi |
| `consolidateAfter` về `2m` | Team Deploy | OPEN | Bản nộp ghi đang 3m |
| Gỡ `do-not-disrupt` khỏi 7 component | Team Deploy | OPEN | Bản nộp ghi chưa làm |
| GitOps sync Healthy sau cleanup | Team Deploy | PENDING | Thực hiện sau hai cleanup action |
| Karpenter tối ưu trở lại | CDO-02 xác nhận | PENDING | Chờ Team Deploy cleanup |

**Cost Optimization verdict:** `GO cho kết quả test; đóng Mandate 02 còn chờ cleanup Karpenter.`

### 3.5 Cost narrative

```text
Node inventory trước/peak/sau lần lượt là 7/7/7.
Cost/hour trước và peak đều là $0.4044/h.
Test kéo dài 0.283333 giờ với test-window cost $0.1146.
Số successful order được chấp nhận là 2327, cost/order khoảng $0.0000493.
Cost/request scoped cho 13,099 checkout+cart request được báo cáo là khoảng $0.00000875/request.
HPA đã về 16 và node giữ baseline 7.
Karpenter cleanup chưa hoàn tất tại thời điểm kết thúc đánh giá.
Cost Optimization đạt cho cửa sổ test vì node/cost-hour không tăng; việc đóng mandate cần hoàn tất cleanup.
```

## 4. Final conclusion

| Trụ cột | Verdict | Evidence chính | Open action |
|---|---|---|---|
| Reliability | GO | HPA 16→22→16; SLO đạt; không incident official run | Không |
| Cost Optimization | GO, closure pending cleanup | 7 node; $0.4044/h; $0.1146; $0.0000493/order | Hoàn nguyên Karpenter |

**CDO-02 final verdict:** `GO cho bài test Mandate 02; trạng thái đóng hoàn toàn PENDING đến khi Team Deploy hoàn nguyên consolidateAfter và gỡ do-not-disrupt.`

Điều kiện GO:

- Reliability: SLO đạt, HPA `16 -> 22 -> 16`, không có OOM/restart/Pending/disruption ảnh hưởng test.
- Cost: node không tăng, phép tính cost tái lập được, pod về baseline và cleanup Karpenter hoàn tất.

### 4.1 Conditional GO rules

`CONDITIONAL GO` chỉ dùng khi SLO và stability đạt nhưng còn action không làm thay đổi kết quả test, có owner và deadline rõ ràng. Không dùng `CONDITIONAL GO` để bỏ qua:

- SLO fail.
- OOM/restart ảnh hưởng request.
- HPA không đạt 22 hoặc không về 16.
- Thiếu node/test-window/order evidence khiến không tính được cost.
- Karpenter cleanup không có owner/deadline.

### 4.2 Open actions

| ID | Trụ cột | Finding | Impact | Owner | Deadline | Exit criteria | Status |
|---|---|---|---|---|---|---|---|
| M02-A01 | Cost Optimization | `consolidateAfter` còn 3m | Karpenter cleanup chưa đúng baseline | Team Deploy | Theo kế hoạch đóng Mandate 02 | NodePool live = 2m | OPEN |
| M02-A02 | Cost Optimization | `do-not-disrupt` còn trên 7 component | Chặn consolidation lâu dài | Team Deploy | Theo kế hoạch đóng Mandate 02 | Annotation không còn trên pod mới | OPEN |

## 5. Evidence index và sign-off

| ID | Trụ cột | Phase | Nội dung | Timestamp | Path/URL |
|---|---|---|---|---|---|
| EV-01 | Reliability/Cost | Before | HPA/pod/node/SLO baseline | ~12:44 15/07/2026 UTC+7 | `docs/postmortem/Mandate02-image/HPAtruoctest.png` |
| EV-02 | Reliability/Cost | Peak | 200 users, HPA=22, SLO, node | 12:45–13:02 15/07/2026 UTC+7 | `docs/postmortem/Mandate02-image/hpataicao.png` |
| EV-03 | Reliability | Test | SLO/5xx và official-run stability | 12:45–13:02 15/07/2026 UTC+7 | SLO dashboard và Prometheus query |
| EV-04 | Cost | Test | Locust/order/cost calculation | 12:45–13:02 15/07/2026 UTC+7 | `docs/postmortem/Mandate02-image/locust.png` và mục Cost Optimization |
| EV-05 | Reliability/Cost | After | HPA=16 và node=7 | ~10 phút sau 13:02 | `docs/postmortem/Mandate02-image/HPAsautest.png` |
| EV-06 | Cost | Cleanup | Karpenter restore | Sau official test | OPEN — chờ Team Deploy hoàn tất |

| Vai trò | Nội dung xác nhận | Trạng thái |
|---|---|---|
| CDO-01 | Locust artifact và official test window | Hoàn tất |
| Team Deploy | Remediation trước test | Hoàn tất |
| Team Deploy | Karpenter cleanup sau test | Còn mở |
| CDO-02 | Reliability/Cost analysis và verdict | Hoàn tất |

## 6. Quality gates của báo cáo

- Không còn trường chưa xác định trong metadata, verdict, SLO, node cost và successful order bắt buộc.
- Evidence index mở được và timestamp khớp test window.
- CDO-01 xác nhận Locust artifact.
- Team Deploy xác nhận remediation/cleanup evidence.
- Công thức cost được reviewer tái tính cho cùng kết quả.
- Narrative không mâu thuẫn với bảng số liệu.
- Final verdict có chữ ký/xác nhận CDO-02.
