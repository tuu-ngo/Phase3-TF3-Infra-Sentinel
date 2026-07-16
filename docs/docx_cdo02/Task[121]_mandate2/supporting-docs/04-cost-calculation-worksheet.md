# Supporting 04 — Cost Calculation Worksheet

## 1. Reliability

Cost calculation chỉ hợp lệ khi Reliability window hợp lệ:

- CDO-01 đạt 200 users trong cửa sổ đã chốt.
- Observability không mất dữ liệu do OOM/restart.
- TEST_START/TEST_END thống nhất giữa Locust và Prometheus.
- Abort test phải dùng ABORT_TIMESTAMP làm TEST_END thực tế.

| Validation | Giá trị | PASS/FAIL |
|---|---|---|
| Peak users | 200 | PASS |
| Test window hợp lệ | 15/07/2026 12:45–13:02 UTC+7, 17 phút | PASS |
| Telemetry continuity | Prometheus và Grafana có dữ liệu xuyên suốt cửa sổ | PASS |
| SLO result có evidence | Checkout 99.9825%, browse/cart 100%, p95 46–48ms | PASS |

## 2. Cost Optimization

### 2.1 Pricing inputs

| Instance type | Capacity type | Region | Quantity | Unit price USD/h | Pricing timestamp | Source |
|---|---|---|---:|---:|---|---|
| t3.large | On-Demand | ap-southeast-1 | 3 | $0.1056 | 15/07/2026 | AWS Pricing API |
| t3.medium | On-Demand | ap-southeast-1 | 1 | $0.0528 | 15/07/2026 | AWS Pricing API |
| t3.small | Spot | ap-southeast-1 | 3 | ~$0.0116 | 15/07/2026 | Giá Spot trung bình 3 AZ |

### 2.2 Node timeline

Tạo segment mới mỗi khi node inventory hoặc applicable unit price thay đổi.

| Segment | Start | End | Duration seconds | Inventory | Cost/hour |
|---|---|---|---:|---|---:|
| S1 | 15/07/2026 12:45 UTC+7 | 15/07/2026 13:02 UTC+7 | 1020 | 7 node không đổi | $0.4044 |

```text
duration_hours_i = duration_seconds_i / 3600
segment_cost_i = cost_per_hour_i * duration_hours_i
test_window_cost = sum(segment_cost_i)
```

| Segment | Duration hours | Cost/hour | Segment cost |
|---|---:|---:|---:|
| S1 | 0.283333 | $0.4044 | $0.1146 |
| **Total** | | | **$0.1146** |

### 2.3 Order reconciliation

| Source | Total checkout | Failure | Successful | Window |
|---|---:|---:|---:|---|
| Locust | 2399 checkout | 0 | 2399 | Locust có thể gồm biên/ramp ngoài window chính xác |
| Prometheus | 2327 PlaceOrder | 0 STATUS_CODE_ERROR | 2327 | Đúng 12:45–13:02 UTC+7 |

```text
locust_success = locust_total - locust_failure
order_delta = abs(locust_success - prometheus_success)
order_delta_pct = order_delta / locust_success * 100
```

| Field | Value |
|---|---:|
| Accepted successful orders | 2327 |
| Source selected | Prometheus PlaceOrder |
| Selection reason | Đúng cửa sổ chính thức; Locust 2399 có chênh lệch biên thời gian/ramp |

### 2.4 Cost/order

```text
cost_per_order = test_window_cost / accepted_successful_orders
```

| Metric | Baseline | Test | Delta | Delta % |
|---|---:|---:|---:|---:|
| Cost/hour | $0.4044 | $0.4044 | $0 | 0% |
| Orders/hour | Không có baseline order cùng window | ~8212.94 | Không so sánh | Không so sánh |
| Cost/order | Không có baseline hợp lệ | ~$0.0000493 | Không so sánh | Không so sánh |

Cost/request theo phạm vi request checkout và cart:

```text
reported_checkout_cart_requests = 2399 + 10700 = 13099
scoped_cost_per_request = $0.1146 / 13099 ≈ $0.00000875/request
```

Giá trị trên chỉ áp dụng cho 13,099 request checkout và cart trong phạm vi đo, không đại diện cho toàn bộ endpoint.

Không điền baseline cost/order nếu không có baseline successful orders trong cửa sổ tương ứng.

### 2.5 Acceptance

- [ ] Node peak không tăng.
- [ ] Cost/hour peak không tăng ngoài biến động Spot price được ghi nhận.
- [ ] Cost/order có input và công thức tái lập được.
- [ ] HPA pod về 16.
- [ ] Node after không cao hơn before.
- [ ] Karpenter cleanup hoàn tất.

**Cost verdict:** `PASS — node và cost/hour không tăng; test-window cost $0.1146; cost/order ~$0.0000493. Cost/request theo phạm vi checkout+cart được báo cáo là ~$0.00000875.`
