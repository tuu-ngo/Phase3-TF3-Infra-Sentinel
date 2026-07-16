# Mandate 02 — CDO-02 Capacity Analysis trước load test 200 users

**Trạng thái tài liệu:** Hoàn tất  
**Namespace:** `techx-tf3`  
**Mục tiêu:** giữ SLO tại 200 concurrent users, HPA co giãn và cost/request không phình.

## 0. Executive summary

Tài liệu này ghi lại phân tích capacity trước khi remediation và trước khi CDO-01 chạy tải. Đây không phải báo cáo kết quả load test. Mục tiêu là xác định hệ thống có đủ điều kiện để bước vào cửa sổ 200 users hay không, rủi ro nào có thể làm sai kết quả và evidence nào phải thu thập để kết luận hai trụ cột Reliability và Cost Optimization.

Capacity được đánh giá ở ba lớp:

1. **Container/pod:** request, limit, OOM và CPU throttling.
2. **Namespace/scheduler:** ResourceQuota, tổng request, số pod và trạng thái Pending.
3. **Node/autoscaling:** allocatable node, Karpenter NodePool, placement và disruption.

Cost được đánh giá theo capacity thực dùng, không suy từ replica count riêng lẻ. Một HPA scale-up không đồng nghĩa node hoặc cost/hour tăng. Vì vậy phải chụp đồng thời HPA, node và NodeClaim tại cùng timestamp.

Kết luận sơ bộ chỉ được ghi sau khi chạy các lệnh live trong tài liệu. Các con số tham chiếu mô tả model kỳ vọng, không thay thế snapshot của lần test hiện tại.

## 0.1 Câu hỏi phân tích

### Reliability

- Tổng CPU/memory request có schedule được ở baseline và projection không?
- Pod quota có đủ cho HPA tăng từ 16 lên 22 và còn headroom vận hành không?
- Container nào có memory limit mỏng và có thể OOM khi telemetry/checkout tăng?
- HPA có nhận metric và có thể tạo replica mới không?
- Checkout pod có được phân tán theo node/zone không?
- Karpenter có thể gây disruption đúng cửa sổ đo SLO không?

### Cost Optimization

- Node capacity hiện tại có đủ để hấp thụ 200 users mà không scale node không?
- Nếu node thay đổi, thời điểm nào làm cost/hour thay đổi?
- Có đủ baseline để chứng minh pod co về 16 và node không neo sau tải không?
- Có đủ dữ liệu để tính cost/order bằng cùng một test window không?

## 0.2 Phương pháp và nguồn evidence

| Nhóm | Phương pháp | Evidence yêu cầu |
|---|---|---|
| HPA | Đọc spec, condition và current/desired replica | `kubectl get hpa`, metrics API |
| Resource | Cộng request/limit theo container | Workload spec và pod JSON live |
| Quota | So used/hard và projection | ResourceQuota live |
| Scheduling | Kiểm tra Pending/events/allocatable | Pod event và node description |
| OOM | So working set với limit, kiểm tra termination | Metrics và container status |
| Karpenter | Đọc NodePool, NodeClaim, events | NodePool/NodeClaim live |
| Cost | Inventory x đơn giá x duration | Node snapshot, pricing source, timestamp |

## 0.3 Giả định và giới hạn

- Projection max giả định HPA có thể scale tới cấu hình max; không khẳng định 200 users sẽ cần 58 HPA pod.
- Mục tiêu thực nghiệm của lần test là tổng HPA pod `16 -> 22 -> 16`, không phải ép toàn bộ HPA lên max.
- Scheduler chỉ bảo đảm request; limit overcommit vẫn có thể gây contention.
- Cost model trong tài liệu chỉ bao gồm compute node nếu scope tài chính không bổ sung storage/network/control plane.
- Spot price và node inventory là dữ liệu theo thời điểm; phải ghi timestamp.
- Metric name trong PromQL có thể cần map theo Prometheus live nhưng semantic và test window phải giữ nguyên.

## 1. Reliability

### 1.1 HPA hot-path

| Service | Min | Max | CPU request | CPU limit | Memory request | Memory limit |
|---|---:|---:|---:|---:|---:|---:|
| frontend-proxy | 2 | 8 | 100m | 500m | 32Mi | 65Mi |
| frontend | 2 | 8 | 100m | 500m | 100Mi | 250Mi |
| product-catalog | 2 | 8 | 100m | 500m | 16Mi | 20Mi |
| cart | 2 | 6 | 100m | 500m | 64Mi | 160Mi |
| checkout | 2 | 8 | 100m | 500m | 16Mi | 20Mi |
| currency | 2 | 6 | 100m | 300m | 8Mi | 20Mi |
| recommendation | 1 | 4 | 100m | 500m | 64Mi | 500Mi |
| product-reviews | 2 | 6 | 100m | 500m | 80Mi | 150Mi |
| ad | 1 | 4 | 100m | 500m | 200Mi | 300Mi |
| **Tổng** | **16** | **58** | | | | |

HPA target là `65%` CPU request. Với request `100m`, ngưỡng mục tiêu tương ứng khoảng `65m/pod`. HPA thêm replica; HPA không tăng CPU hoặc memory cho pod hiện hữu.

Kiểm tra live:

```powershell
$NS='techx-tf3'
kubectl -n $NS get hpa
kubectl -n $NS get hpa -o yaml
kubectl -n $NS get --raw '/apis/metrics.k8s.io/v1beta1/namespaces/techx-tf3/pods'
```

### 1.2 Tổng capacity

| Trạng thái | Pod | CPU request | CPU limit | Memory request | Memory limit |
|---|---:|---:|---:|---:|---:|
| 9 HPA tại min | 16 | 1.6 vCPU | 7.6 vCPU | 896Mi | 2170Mi |
| 9 HPA tại max | 58 | 5.8 vCPU | 27.8 vCPU | 3280Mi | 8020Mi |
| Workload cố định tham chiếu | 23 | 1.55 vCPU | 7.0 vCPU | 5456Mi | 8723Mi |
| Namespace baseline tham chiếu | 39 | 3.15 vCPU | 14.6 vCPU | ~6350Mi | ~10900Mi |
| Namespace nếu HPA đạt max | 81 | 7.35 vCPU | 34.8 vCPU | 8736Mi | 16743Mi |

Ý nghĩa:

- Scheduler dùng request, không dùng limit.
- CPU request `7.35 vCPU` tại max phải nhỏ hơn tổng allocatable/node burst live.
- CPU limit `34.8 vCPU` có thể overcommit phần cứng và gây throttling/p95 spike.
- Memory quota tổng có thể còn dư nhưng container vẫn OOM nếu vượt limit riêng.

#### Cách đọc request và limit

`request` trả lời câu hỏi scheduler có đặt được pod hay không. `limit` trả lời container có thể sử dụng tối đa bao nhiêu trước khi bị CPU throttle hoặc memory OOMKill. Hai giá trị không được cộng chung để kết luận scheduling.

Ví dụ: tổng CPU request projection `7.35 vCPU` có thể nhỏ hơn scheduling envelope, nhưng tổng CPU limit `34.8 vCPU` vẫn lớn hơn năng lực vật lý. Trong trường hợp đó pod vẫn có thể Running nhưng p95 tăng do nhiều container tranh CPU tại peak. Vì vậy evidence phải chứa cả `Pending/FailedScheduling` và CPU throttling ratio.

#### Headroom cần xác nhận live

| Dimension | Công thức | Giá trị live | Ngưỡng đánh giá |
|---|---|---:|---|
| Pod quota headroom | `100 - 42` | 58 pod sau remediation | `>=6`, đạt |
| CPU request headroom | `~17.8 - 7.35` | ~10.45 vCPU tại projection max | Dương, đạt về scheduling |
| Memory quota headroom | `16Gi - 7124Mi` request | ~9.04Gi | Dương, đạt |
| Memory limit quota headroom | `24Gi - 13190Mi` | ~11.12Gi | Dương, đạt |

### 1.3 Pod quota

Expected state:

```yaml
hard:
  pods: "100"
```

Tại projection 81 pod, quota 100 còn headroom 19 pod. Với mục tiêu peak 22 HPA-managed pod, namespace cần ít nhất 6 slot tăng thêm so với baseline HPA 16.

```powershell
kubectl -n $NS get resourcequota -o yaml
kubectl -n $NS get pods --field-selector=status.phase=Pending -o wide
kubectl -n $NS get events --sort-by=.lastTimestamp
```

### 1.4 Node capacity và Karpenter

Capacity tham chiếu:

- 3 node tĩnh `t3.large`.
- Allocatable khoảng `1.93 vCPU` và `7.08Gi/node`.
- Tổng CPU node tĩnh khoảng `5.79 vCPU`.
- Karpenter NodePool burst limit `12 vCPU/48Gi`.
- Tổng scheduling envelope khoảng `17.8 vCPU`.

Phải chụp lại live inventory; số tham chiếu không được dùng làm bằng chứng test mới.

```powershell
kubectl get nodes -o custom-columns='NODE:.metadata.name,TYPE:.metadata.labels.node\.kubernetes\.io/instance-type,CAPACITY_TYPE:.metadata.labels.karpenter\.sh/capacity-type,ZONE:.metadata.labels.topology\.kubernetes\.io/zone,CPU:.status.allocatable.cpu,MEMORY:.status.allocatable.memory,PODS:.status.allocatable.pods'
kubectl get nodeclaims -o wide
kubectl describe nodes
kubectl top nodes
```

### 1.5 OOM và memory pressure

Component cần kiểm tra:

| Component | Expected request | Expected limit | Rủi ro |
|---|---:|---:|---|
| Prometheus | 450Mi | 1200Mi | Metric volume tăng |
| OpenSearch | 750Mi | 1600Mi | Log/indexing tăng |
| Kafka | 650Mi | 1.5Gi | Buffer/message tăng |
| Jaeger | 750Mi | 2Gi | Trace volume; từng có nguy cơ Exit 137 |
| OTel Collector | Live manifest | 350Mi | Trace/metric pipeline saturation |
| payment | Live manifest | 300Mi | Checkout critical, không HPA |
| shipping | Live manifest | 64Mi | Không HPA |
| quote | Live manifest | 80Mi | Không HPA |

```powershell
kubectl -n $NS get pods -o custom-columns='POD:.metadata.name,RESTARTS:.status.containerStatuses[*].restartCount,LAST_REASON:.status.containerStatuses[*].lastState.terminated.reason,LAST_EXIT:.status.containerStatuses[*].lastState.terminated.exitCode'
```

### 1.6 Scheduling và checkout spread

Expected state:

- Hostname: soft constraint, `ScheduleAnyway`.
- Zone: hard constraint, `DoNotSchedule`.
- Checkout replica không tập trung toàn bộ trên một node.

```powershell
kubectl -n $NS get deployment checkout -o jsonpath='{.spec.template.spec.topologySpreadConstraints}'
kubectl -n $NS get pods -l app=checkout -o wide
```

### 1.7 Reliability risk register

| ID | Risk | Trigger | Signal | Impact | Priority |
|---|---|---|---|---|---|
| REL-R01 | Quota chặn HPA | Pod hard limit hết | Exceeded quota/Pending | Không scale, mất SLO | Critical |
| REL-R02 | CPU overcommit | Nhiều pod dùng gần limit | Throttling ratio, p95 | Latency spike | High |
| REL-R03 | OOM | Working set chạm limit | OOMKilled/restart | Mất request/telemetry | Critical |
| REL-R04 | FailedScheduling | Thiếu CPU/memory/topology | Pending event | Không đạt 22 pod | Critical |
| REL-R05 | Checkout cùng node | Placement không spread | Pod/node mapping | Mất nhiều replica | High |
| REL-R06 | Karpenter eviction | Consolidation trong test | Disruption event | 5xx/p95 spike | Critical |
| REL-R07 | HPA mất metric | metrics-server lỗi | `<unknown>` | Không scale | Critical |

### 1.8 Failure-mode interpretation

| Quan sát | Root cause khả dĩ | Không nên kết luận vội | Kiểm tra tiếp |
|---|---|---|---|
| Pod Pending | Quota, CPU/memory, topology, taint | Node thiếu capacity ngay lập tức | Pod event/FailedScheduling reason |
| p95 tăng, không Pending | CPU throttle, downstream saturation | HPA không hoạt động | Throttling, HPA desired/current, dependency latency |
| Restart delta tăng | OOM, crash, probe failure | Luôn là OOM | Last termination reason/exit code |
| HPA không tăng | Metric thấp, mất metric, max reached | HPA hỏng | HPA condition và CPU current/target |
| 5xx tăng khi node event | Karpenter disruption hoặc rollout | App regression | NodeClaim/event/pod termination timeline |

## 2. Cost Optimization

### 2.1 Baseline inventory

| Trường | Giá trị |
|---|---|
| Region | `ap-southeast-1` |
| Timestamp | 15/07/2026, trước test ~12:44 UTC+7 |
| Node count | 7 |
| On-Demand node | 4 |
| Spot node | 3 |
| Instance types | 3×t3.large, 1×t3.medium, 3×t3.small Spot |
| Cost/hour | $0.4044/h |
| HPA-managed pod baseline | 16 |

Đơn giá phải ghi region, capacity type, nguồn và thời điểm tra giá. Không dùng giá Spot của vùng hoặc thời điểm khác.

### 2.2 Cost model

```text
node_hourly_cost = sum(node_quantity_i * unit_price_i)
segment_cost = segment_hourly_cost * segment_duration_seconds / 3600
test_window_cost = sum(segment_cost)
cost_per_order = test_window_cost / successful_orders
```

Nếu node inventory không đổi, test-window cost bằng baseline cost/hour nhân thời lượng test. Nếu node thay đổi, chia timeline thành các segment.

### 2.3 Cost risk register

| ID | Risk | Signal | Impact | Priority |
|---|---|---|---|---|
| COST-R01 | Node tăng tại peak | Node/NodeClaim count | Cost/hour tăng | High |
| COST-R02 | Pod không về 16 | HPA replica after | Neo request sau test | High |
| COST-R03 | `do-not-disrupt` không gỡ | Annotation live | Karpenter không tối ưu | High |
| COST-R04 | `consolidateAfter` không về 2m | NodePool live | Capacity dư tồn tại lâu | High |
| COST-R05 | Order count lệch window | Locust/Prometheus delta | Cost/order sai | High |

### 2.4 Capacity-to-cost interpretation

Cost/hour chỉ thay đổi khi thành phần được tính phí thay đổi, chủ yếu là node count/type/capacity type. HPA tăng từ 16 lên 22 trên cùng node inventory không làm compute cost/hour tăng, nhưng chứng minh hạ tầng hiện tại sử dụng phần capacity dự phòng hiệu quả hơn.

Các trường hợp kết luận:

| Quan sát | Kết luận cho phép |
|---|---|
| Pod tăng, node không tăng | Pod autoscaling hoạt động; compute cost/hour không tăng |
| Pod tăng, node tăng | Tính segment cost; đánh giá incremental cost và SLO |
| Pod về 16, node chưa giảm | Kiểm tra node có phải baseline node hay capacity dư do Karpenter |
| Node không tăng nhưng p95 fail | Không thể dùng cost thấp để kết luận mandate đạt |
| Thiếu baseline order | Không được tuyên bố cost/order giảm/không phình |

## 3. Capacity readiness summary

| Trụ cột | Check | Expected | Trạng thái | Evidence |
|---|---|---|---|---|
| Reliability | Pod quota | 100 | PASS | Live hard quota 100 sau PR #105 |
| Reliability | HPA metrics | 9/9 hoạt động | PASS | 9 HPA, CPU target 65% |
| Reliability | CPU scheduling headroom | Đủ cho projection | PASS | 7.35 vCPU request vs ~17.8 vCPU envelope |
| Reliability | Memory/OOM headroom | Không OOM tái diễn | PASS sau remediation | Request 7124Mi/16Gi; limit 13190Mi/24Gi; Jaeger và observability đã tăng limit |
| Reliability | Checkout spread | Hostname + zone | PASS | Hostname soft và zone hard sau PR #107 |
| Cost | Baseline inventory | Đầy đủ | PASS | 7 node: 4 On-Demand/3 Spot |
| Cost | Baseline cost/hour | Tái lập được | PASS | AWS Pricing API ap-southeast-1, $0.4044/h |

## 4. Kết luận trước remediation

### 4.1 Reliability conclusion form

```text
CPU scheduling capacity: PASS — 7.35 vCPU request projection vs ~17.8 vCPU envelope
Memory/request headroom: PASS — 7124Mi/16Gi request, 13190Mi/24Gi limit sau remediation
Pod quota headroom: PASS — hard 100, used snapshot 42
HPA metric readiness: PASS — 9/9 HPA đọc CPU metric, target 65%
OOM/Pending risk: Mitigated — resource đã tăng; không phát sinh lỗi trong lần test chính thức
Checkout placement: PASS — topology spread hostname/zone đã áp dụng
Karpenter disruption risk: Mitigated trong test bằng guardrail tạm thời
Reliability readiness: READY
```

### 4.2 Cost conclusion form

```text
Baseline node inventory captured: YES — 7 node
Baseline cost/hour reproducible: YES — $0.4044/h
Scale-down baseline defined: YES — 16 HPA-managed pod
Order-count contract defined: YES — Prometheus PlaceOrder đúng cửa sổ test
Cost measurement readiness: READY
```

### 4.3 Điều kiện chuyển sang remediation plan

- Mỗi gap có risk ID và evidence live.
- Expected state có thể kiểm tra bằng lệnh read-only.
- Gap cần thay đổi manifest được `(Bàn giao Team Deploy)`.
- Gap liên quan test window/Locust được `(Bàn giao CDO-01)`.
- Không chuyển sang GO khi Critical risk chưa có mitigation hoặc acceptance criteria.
