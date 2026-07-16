# Mandate 02 — CDO-02 Remediation Plan trước load test 200 users

**Trạng thái tài liệu:** Hoàn tất; còn action cleanup sau test  
**Nguyên tắc:** CDO-02 đề xuất và xác nhận; Team Deploy triển khai; CDO-01 sở hữu tải.

## 0. Executive summary

Tài liệu chuyển các gap trong capacity analysis thành solution có owner, expected state, acceptance criteria, rollback/cleanup và evidence. Mục tiêu không chỉ là “đã sửa manifest”, mà là chứng minh solution đã xuất hiện trên live cluster và không tạo rủi ro mới cho Reliability hoặc Cost Optimization.

CDO-02 không trực tiếp sửa production manifest. CDO-02 chịu trách nhiệm:

- Mô tả root cause/risk và tác động đến SLO/cost.
- Định nghĩa expected state và phép kiểm tra.
- Mở bàn giao đúng owner.
- Xác nhận live state sau deploy.
- Phát hành GO/NO-GO cho cửa sổ 200 users.

Team Deploy chịu trách nhiệm thay đổi source-of-truth, merge/deploy/sync và rollback. CDO-01 chịu trách nhiệm chạy/dừng tải và cung cấp artifact đúng cửa sổ.

## 0.1 Nguyên tắc lựa chọn solution

### Reliability

- Ưu tiên loại bỏ blocker cứng trước: quota, missing metric, FailedScheduling.
- Mitigate failure mode đã biết: OOM, checkout co-location, Karpenter disruption.
- Không tăng resource thiếu căn cứ cho toàn bộ service; chỉ thay đổi component có risk/evidence.
- Mọi protection tạm thời phải có cleanup owner và deadline.

### Cost Optimization

- Không scale node trước chỉ để tạo dư capacity nếu baseline hiện tại đủ.
- Không giữ `do-not-disrupt` lâu hơn cửa sổ test và cooldown.
- Không để timer consolidation tạm thời trở thành cấu hình vĩnh viễn.
- Cost comparison phải dùng cùng scope và cùng test window.

## 0.2 Definition of Done cho một remediation

Một remediation chỉ được đánh dấu `VALIDATED` khi đủ:

1. Có risk/gap ID.
2. Có PR/commit tại source-of-truth.
3. GitOps sync thành công.
4. Live state khớp expected state.
5. Acceptance command/query PASS.
6. Không tạo Critical regression mới.
7. Có rollback hoặc cleanup action nếu thay đổi tạm thời.

## 1. Reliability

### 1.1 Solution matrix

| ID | Gap | Solution | Expected state | Acceptance criteria | Owner |
|---|---|---|---|---|---|
| REL-S01 | Pod quota có thể chặn HPA | Tăng quota | `hard.pods=100` | Live quota = 100, không Exceeded quota | Team Deploy |
| REL-S02 | Observability memory thấp | Tăng request/limit | Theo capacity analysis | Pod Ready, không OOM, có headroom | Team Deploy |
| REL-S03 | payment/shipping/quote limit thấp | Tăng memory limit | 300/64/80Mi | Không restart/OOM khi tải | Team Deploy |
| REL-S04 | Checkout thiếu fault-domain spread | Thêm topology spread | Hostname soft, zone hard | Replica phân tán và schedule được | Team Deploy |
| REL-S05 | Karpenter evict critical workload | Thêm annotation tạm | 7 component `do-not-disrupt=true` | Không eviction trong test | Team Deploy |
| REL-S06 | Consolidation ảnh hưởng test | Điều chỉnh timer tạm | Giá trị test phê duyệt, tham chiếu 3m | NodePool live đúng | Team Deploy |

7 component critical: `cart`, `checkout`, `payment`, `shipping`, `quote`, `postgresql`, `valkey-cart`.

### 1.1.1 Chi tiết solution và trade-off

#### REL-S01 — Pod quota 100

Quota 100 cho phép projection 81 pod còn headroom. Giá trị này không tự tạo pod và không làm tăng cost; nó chỉ loại bỏ blocker admission khi HPA cần tăng replica. Rủi ro sau khi mở quota là CPU limit overcommit có cơ hội xuất hiện rõ hơn, do đó phải giám sát throttling và node saturation.

#### REL-S02/REL-S03 — Memory sizing

Tăng memory limit giảm xác suất OOM nhưng không bảo đảm scheduling nếu request tăng vượt node headroom. Team Deploy phải bàn giao cả request và limit đã render. CDO-02 kiểm tra working set/limit trong peak; không chỉ xác nhận pod Ready trước test.

#### REL-S04 — Checkout topology spread

Hostname soft constraint tránh Pending khi cluster không đủ node phù hợp. Zone hard constraint bảo đảm không dồn checkout vào một zone khi topology cho phép. CDO-02 phải kiểm tra placement live, vì manifest đúng chưa chứng minh scheduler đã phân tán pod như mong đợi.

#### REL-S05/REL-S06 — Karpenter protection

`do-not-disrupt` bảo vệ workload critical trong cửa sổ đo. `consolidateAfter` kiểm soát tốc độ consolidation ở cấp NodePool. Hai cơ chế phục vụ Reliability trong test nhưng có thể cản Cost Optimization nếu không cleanup. Vì vậy chúng luôn đi kèm COST-C01/COST-C02.

**(Bàn giao Team Deploy):** thực hiện REL-S01..REL-S06 tại source-of-truth; trả PR/commit, rendered manifest, GitOps sync status và live output. Không dùng `kubectl patch` làm trạng thái lâu dài.

### 1.2 Pre-test validation

```powershell
$NS='techx-tf3'
kubectl -n $NS get resourcequota
kubectl -n $NS get hpa
kubectl -n $NS get pods -o wide
kubectl -n $NS get events --sort-by=.lastTimestamp
kubectl get nodes -o wide
kubectl get nodeclaims -o wide
kubectl get nodepool flash-sale-spot -o yaml
```

- [ ] Pod quota = 100.
- [ ] 9 HPA có CPU metric, target 65%, tổng min 16/max 58.
- [ ] Không có Pending/FailedScheduling.
- [ ] Không có CrashLoopBackOff hoặc OOM tái diễn.
- [ ] Resource live đạt expected request/limit.
- [ ] Checkout spread đúng hostname/zone.
- [ ] 7 component có `do-not-disrupt=true`.
- [ ] Không có Karpenter disruption đang chạy.
- [ ] Baseline SLO đạt.

### 1.2.1 Validation record

| Solution | Git revision | GitOps health | Live expected state | Regression check | Verdict |
|---|---|---|---|---|---|
| REL-S01 | PR #105 | Healthy | Pod quota 100 | Không Exceeded quota trong test | VALIDATED |
| REL-S02 | PR #105 và thay đổi tiếp theo | Healthy | Observability limits đã tăng | Không OOM trong test chính thức | VALIDATED |
| REL-S03 | PR #107 | Healthy | payment 300Mi, shipping 64Mi, quote 80Mi | Không OOM/restart do tải | VALIDATED |
| REL-S04 | PR #107 | Healthy | Checkout hostname/zone spread | Pod hoạt động ổn định | VALIDATED |
| REL-S05 | Thay đổi trước test | Healthy | 7 component được bảo vệ | Không critical eviction trong test | VALIDATED; cleanup còn mở |
| REL-S06 | PR #107 và điều chỉnh sau đó | Healthy | consolidateAfter 3m trong thời điểm report | Test ổn định | VALIDATED; phải hoàn nguyên 2m |

Verdict hợp lệ: `PROPOSED`, `DEPLOYED`, `VALIDATED`, `REJECTED`, `ROLLED_BACK`.

### 1.3 Abort thresholds

| Signal | Abort condition | Hành động |
|---|---|---|
| OOM | OOMKilled mới ở checkout/datastore/observability | `(Bàn giao CDO-01)` dừng tải; thu event/restart delta |
| Pending | HPA pod Pending >2 phút do capacity/quota/topology | Dừng tải; `(Bàn giao Team Deploy)` xử lý root cause |
| Storefront p95 | `>=1s` kéo dài | Dừng tải và chụp throttling/node saturation |
| Checkout success | `<99%` | Dừng tải, đối chiếu 5xx/trace |
| Browse/cart success | `<99.5%` | Dừng tải, đối chiếu endpoint telemetry |
| Karpenter | Eviction critical workload | Dừng tải; lưu disruption timeline |

## 2. Cost Optimization

### 2.1 Cost controls trước test

- Chụp node inventory và HPA baseline tại T-5.
- Chốt region, On-Demand/Spot unit price và pricing timestamp.
- Dùng một TEST_START/TEST_END cho Locust và Prometheus.
- Không ép scale node để tạo evidence; ghi nhận hành vi thật ở 200 users.
- Chốt công thức segment cost trước test.

### 2.1.1 Cost measurement boundary

| Thành phần | Trong scope mặc định | Ghi chú |
|---|---|---|
| Worker node compute | Yes | On-Demand và Spot theo inventory |
| EKS control plane | No | Chỉ thêm nếu mandate yêu cầu full platform cost |
| EBS/storage | No | Ghi riêng nếu thay đổi do test |
| Network/data transfer | No | Ghi riêng nếu có dữ liệu đáng kể |
| Observability managed service | No | Workload chạy trên node đã nằm trong compute |

Không thay đổi scope giữa baseline và test.

### 2.2 Handoff CDO-01

**(Bàn giao CDO-01):**

- Chạy 200 concurrent users trong cửa sổ chính thức.
- Reset Locust stats trước cửa sổ nếu có ramp thử.
- Cung cấp TEST_START, TEST_END, timezone và spawn rate.
- Cung cấp Locust stats/failures/exceptions CSV.
- Cung cấp checkout total/failure/success.
- Xác nhận tải đã dừng trước cleanup.

### 2.3 Cleanup plan

Chỉ bắt đầu khi CDO-01 xác nhận tải dừng, HPA về 16 và không có recovery/rollout đang chạy.

| ID | Action | Owner triển khai | CDO-02 xác nhận |
|---|---|---|---|
| COST-C01 | Hoàn nguyên `consolidateAfter` về `2m` | Team Deploy | NodePool live = 2m |
| COST-C02 | Gỡ `do-not-disrupt` khỏi 7 component | Team Deploy | Annotation không còn trên pod mới |
| COST-C03 | Sync GitOps | Team Deploy | Application/workload Healthy |
| COST-C04 | Theo dõi consolidation | Team Deploy/CDO-02 | Karpenter tối ưu lại, không lỗi workload |

**(Bàn giao Team Deploy sau test):** triển khai COST-C01..C03 và trả PR/commit, GitOps sync status, live NodePool/pod annotation evidence.

### 2.4 Rollback và exception handling

| Tình huống | Quyết định | Owner | Evidence |
|---|---|---|---|
| Resource mới gây Pending | Rollback/điều chỉnh request | Team Deploy | Event và rollout status |
| Topology hard constraint không schedule được | Dừng test, review topology | Team Deploy/CDO-02 | FailedScheduling reason |
| Protection annotation chặn recovery cần thiết | Quyết định exception có kiểm soát | Team Deploy/CDO-02 | Incident timeline |
| Cleanup làm workload mất ổn định | Rollback cleanup, giữ incident evidence | Team Deploy | GitOps/health output |

Mọi exception phải có timestamp, approver, lý do và thời hạn hết hiệu lực.

## 3. Execution order

1. CDO-02 hoàn tất capacity analysis và mở handoff remediation.
2. Team Deploy triển khai solution và bàn giao evidence.
3. CDO-02 kiểm tra live state, phát hành GO/NO-GO Reliability/Cost.
4. CDO-01 chạy 200 users.
5. CDO-02 theo dõi Reliability/Cost và thu before/peak/after.
6. CDO-01 dừng tải, bàn giao Locust artifact.
7. CDO-02 đối chiếu Locust với Prometheus/Grafana, tính cost/order.
8. Team Deploy cleanup Karpenter; CDO-02 xác nhận.
9. CDO-02 hoàn thiện load-test report.

## 4. GO/NO-GO form

| Trụ cột | Check | PASS/FAIL | Evidence | Handoff nếu FAIL |
|---|---|---|---|---|
| Reliability | Quota/HPA/resource/spread/Karpenter | PASS | Remediation validation + kết quả test | Không cần trước test; cleanup giao Team Deploy |
| Reliability | Baseline SLO | PASS | Checkout 99.9825%, browse/cart 100%, p95 46–48ms | Không |
| Cost | Node/cost baseline | PASS | 7 node, $0.4044/h | Không |
| Cost | Test-window contract | PASS | 15/07/2026 12:45–13:02 UTC+7 | CDO-01 đã cung cấp |

**GO/NO-GO:** `GO cho lần test chính thức; đóng mandate còn phụ thuộc cleanup Karpenter.`

## 5. Decision log và handoff tracking

| ID | Timestamp | Decision | Cơ sở kỹ thuật | Owner | Status |
|---|---|---|---|---|---|
| M02-D01 | Trước 15/07/2026 | Tăng quota/resource, thêm spread và bảo vệ Karpenter trước official test | OOM/disruption/quota risks từ readiness và các lần thử trước | CDO-02 đề xuất, Team Deploy thực hiện | VALIDATED |
| M02-D02 | Sau test 15/07/2026 | Hoàn nguyên Karpenter về baseline | Protection tạm thời cản cost optimization | Team Deploy | OPEN |

| Handoff ID | From | To | Input | Output yêu cầu | Due | Status |
|---|---|---|---|---|---|---|
| M02-HO-DEP-01 | CDO-02 | Team Deploy | REL-S01..S06 | PR/sync/live evidence | Trước 15/07/2026 | DONE |
| M02-HO-CDO01-01 | CDO-02 | CDO-01 | Test contract | Locust artifact/window | 15/07/2026 | DONE |
| M02-HO-DEP-02 | CDO-02 | Team Deploy | COST-C01..C03 | Cleanup evidence | Sau official test | OPEN |

## 6. Điều kiện chuyển sang load-test report

- GO/NO-GO đã có timestamp và evidence.
- Critical remediation đều `VALIDATED`.
- CDO-01 xác nhận test contract và artifact format.
- Baseline node/cost/HPA đã chụp.
- Abort channel và owner đã xác định.
- Cleanup handoff đã có owner trước khi bắt đầu tải.
