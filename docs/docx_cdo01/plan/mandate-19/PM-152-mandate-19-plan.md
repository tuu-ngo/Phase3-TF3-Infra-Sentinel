# PM-152 — Mandate #19: Canonical Breakpoint and Old-Ceiling Plan

| Field | Value |
|---|---|
| Jira | PM-152, thuộc PM-151 — Mandate #19 Throughput Ceiling |
| Owner | Hoàng Công Trí Dũng |
| Dependency | PM-143 exact SLO budget; PM-144/145 stable; PM-155 freeze coordination |
| Output consumer | PM-153 tuning và PM-155 final demo/ADR |
| Document state | `EXECUTION PLAN`; không phải runtime evidence hoặc kết luận PM-152 Done |

## 1. Mục tiêu và verdict contract

PM-152 phải đo được **trần tải bền cũ** trên một node set cố định và xác định bottleneck bão hòa sớm nhất bằng metric cộng trace. Không dùng số user, CCU hoặc điểm max tức thời trên Grafana làm `old_ceiling`.

```text
old_ceiling = served RPS trung bình cao nhất trong một stage >= 5 phút
              mà mọi SLO và correctness gate giữ trong toàn stage
```

Stage đầu tiên sau đó là breakpoint khi một trong hai điều kiện xảy ra:

1. một SLO fail trong **hai cửa sổ 1 phút liên tiếp**; hoặc
2. offered load tiếp tục tăng nhưng served RPS plateau, đồng thời có saturation signal cụ thể.

Breakpoint phải được tái hiện ít nhất một lần. Nếu không tái hiện, kết quả là `INCONCLUSIVE`, không chọn run đẹp nhất.

## 2. Canonical load protocol

### 2.1 Một tool và một profile riêng

Chỉ dùng **Locust**, version-pin trực tiếp trong `phase3 - information/techx-corp-platform/src/load-generator/requirements.txt`. Tạo profile Mandate 19 riêng; không dùng nguyên `WebsiteUser` hiện tại vì profile đó:

- dùng `wait_time = between(1, 10)`, nên user không tương đương RPS;
- gọi recommendation, review, AI và ads;
- đọc flagd để tạo homepage flood;
- làm external dependency và flag state trở thành nhiễu capacity.

Profile chính thức phải điều khiển **offered RPS** bằng custom load shape/constant-throughput behavior, chạy headless, xuất CSV và giữ nguyên Git SHA giữa before/after. Không dùng UI để thay traffic mix giữa run.

### 2.2 Traffic mix cố định

Canonical transaction mix cho PM-152/153/154/155:

| Transaction | Weight | Requests |
|---|---:|---|
| Browse product | 70% | `GET /api/products/<id>` |
| Read cart | 20% | `GET /api/cart` |
| Checkout journey | 10% | `GET /api/products/<id>` -> `POST /api/cart` -> `POST /api/checkout` |

AI, recommendation, reviews, ads, browser traffic và flagd mutation đều bị loại khỏi capacity profile. Nếu PM/mentor duyệt traffic mix khác, ghi exact mix/version trước run đầu và dùng cùng mix cho toàn bộ before/after; không sửa giữa PM-152 và PM-153.

Load generator phải chạy ngoài EKS node set được đo. Nếu buộc phải chạy trong cluster, run mang verdict `INVALID_LOAD_GENERATOR_SHARED_CAPACITY` trừ khi owner chứng minh nó nằm trên node pool tách biệt và không tranh CPU/memory/network với workload under test.

### 2.3 Stage schedule

1. Smoke: 1 phút ở tải thấp; không tính vào kết quả.
2. Warm-up: 5 phút ở `R0`, bỏ dữ liệu warm-up khỏi ceiling.
3. Stages: mỗi stage 5 phút, target offered RPS tăng 25%: `R(n+1) = ceil(R(n) * 1.25)`.
4. Giữ stage cho đủ 5 phút; không tăng sớm vì biểu đồ đang xanh.
5. Khi breakpoint xảy ra, dừng tăng tải an toàn, hạ tải và đợi recovery.
6. Chạy lại highest-passing stage một lần và failing stage một lần để xác nhận boundary.

`R0` lấy từ một calibration run không dùng làm evidence, sao cho các SLO còn headroom rõ và hệ đã warm. Record exact `R0`; không dùng “thêm 50 user/phút”.

## 3. SLO, abort và correctness gates

| Gate | Pass trong từng cửa sổ 1 phút và toàn stage |
|---|---|
| Checkout success | `>= 99.0%` |
| Browse success | `>= 99.5%` |
| Cart success | `>= 99.5%` |
| Browse storefront p95 | `< 1000 ms` |
| Checkout p99 | `< 300 ms`, theo PM-143 hiện có; PM owner phải xác nhận trước official run |
| Browse p99 | Exact value do PM/mentor approve và record trước run; thiếu value -> `BLOCKED_SLO_CONTRACT` |
| Unexpected errors | `5xx + timeout`; `429` chỉ được tách riêng ở PM-154, không tính là success |
| Pod health | không OOM, restart hoặc unready do load |
| Correctness | duplicate order/payment `= 0`; expected event reconciliation pass |

Không dùng ngưỡng error chung `>1%`: Browse/Cart đã fail ngay dưới `99.5%`. Abort ngay khi có safety event như OOM/restart, datastore critical saturation, node replacement/Spot interruption, load generator saturation hoặc data-correctness failure. Run abort vì safety là `FAILED_SAFE`, không tự suy ra old ceiling.

Dashboard rolling `[24h]` chỉ dùng theo dõi vận hành, không quyết định breakpoint. Source of truth là raw Locust CSV và Prometheus query với exact `[start,end]`/range query của stage. Screenshot Grafana chỉ là presentation artifact.

## 4. Node-set invariance và change freeze

Node count bằng nhau chưa đủ. Canonical node-set record gồm:

```text
node name + metadata.uid + spec.providerID + instance type + availability zone
```

Collector phải:

1. sort record ổn định và tạo SHA-256 trước run;
2. sample lại mỗi 30 giây;
3. lưu raw node JSON và timeline;
4. so hash before/after và giữa PM-152/153/154.

Freeze Karpenter scale-up và voluntary disruption bằng thay đổi GitOps có review, có rollback, và giới hạn đúng capacity đã chụp. Không chỉ dựa vào `budgets` hiện tại vì node provisioning vẫn có thể xảy ra. Bất kỳ NodeClaim mới, node name/UID/providerID/type/AZ đổi, Spot interruption hoặc replacement nào đều làm run `INVALID_NODE_SET_CHANGED`.

Freeze thêm: application images/config, HPA/resources, NetworkPolicy, RBAC, Envoy, datastore, observability, feature flags, backup/restore và deployment khác trong cửa sổ test. Capture `BASE_SHA`, image digests và Argo revision.

## 5. Dashboard và raw evidence

Tạo dashboard Mandate 19 theo exact test window, tối thiểu có:

- offered RPS từ Locust và served RPS tại frontend-proxy/frontend;
- success/error/429 theo cửa sổ 1 phút;
- browse/cart/checkout p95 và p99;
- HPA desired/current/max và Ready replicas;
- CPU usage, CPU throttling, memory, GC và restarts;
- node count, node-set hash timeline và RPS/node;
- DB pool `Open/InUse/WaitCount/WaitDuration`, PostgreSQL connections;
- Envoy pending/overflow/upstream metrics;
- queue depth/lag của MSK và ElastiCache health;
- load generator CPU/network/target-vs-actual RPS.

Raw Prometheus range-query result, Locust CSV, node snapshot/timeline và trace JSON là source of truth. Mọi file ghi UTC start/end, Git SHA, image digests, Locust/version/profile SHA và query.

## 6. Bottleneck protocol không thiên kiến

Không mở đầu bằng giả thuyết `product-catalog` hoặc pool 20. Candidate matrix bắt buộc:

| Candidate | Signals tối thiểu |
|---|---|
| frontend-proxy / frontend | request rate, p99, CPU/throttle, replicas, pending/overflow |
| product-catalog / product-reviews | request/p99, CPU/GC, DB pool wait, query/connection pressure |
| cart / checkout / payment / shipping | request/p99, CPU/GC, replicas, downstream errors, trace critical path |
| RDS | active/max connections, waits, CPU, I/O, latency |
| ElastiCache | connections, CPU, latency, evictions/errors |
| MSK | produce latency/errors, queue/consumer lag |
| load generator | target/actual RPS, CPU/network saturation |

Kết luận là **bottleneck bão hòa sớm nhất**. Co-bottleneck phải được liệt kê với evidence; chọn một bottleneck chính để PM-153 nới, không ép hệ chỉ có đúng một bottleneck.

## 7. Evidence contract và DoD

Output đề xuất:

```text
docs/evidence/mandate-19/pm-152/
  environment.json
  load-profile.json
  locust/{run-1,run-2}/
  prometheus/{run-1,run-2}/
  nodes/{before.json,timeline.jsonl,after.json,node-set.sha256}
  traces/
  breakpoint-summary.json
  closure-checklist.md
```

PM-152 chỉ `Done` khi:

- canonical tool/profile/version/traffic mix được chốt;
- SLO có exact p99 contract, không còn placeholder;
- highest passing stage kéo dài đủ 5 phút và được re-run;
- failing stage/breakpoint được tái hiện ít nhất một lần;
- old ceiling dùng sustained served RPS, không dùng spike/max Grafana;
- node-set hash không đổi và load generator không tranh capacity;
- raw Locust + exact-window Prometheus + trace đủ;
- earliest bottleneck có saturation metric + trace; co-bottleneck được ghi nhận;
- correctness pass, không duplicate/mất event;
- recovery sau hạ tải được xác nhận;
- không deployment/config/flag/backup interference.

Thiếu bất kỳ gate nào: PM-152 trả `BLOCKED` hoặc `INCONCLUSIVE`, không bàn giao số cho PM-153/155.
