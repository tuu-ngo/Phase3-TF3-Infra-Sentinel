# Supporting 02 — Evidence Collection Checklist

## 1. Reliability

### 1.1 Naming convention

```text
<TEST_ID>_<PHASE>_<SIGNAL>_<YYYYMMDD-HHMMSS+0700>.<ext>
```

Ví dụ:

```text
mandate02-20260716_before_hpa_20260716-124000+0700.txt
mandate02-20260716_peak_slo_20260716-125500+0700.png
mandate02-20260716_after_pods_20260716-132000+0700.txt
```

### 1.2 Required evidence

| ID | Phase | Signal | Bắt buộc | Trạng thái | Path |
|---|---|---|---|---|---|
| REL-EV-01 | Before | HPA và tổng replica=16 | Yes | TBD | TBD |
| REL-EV-02 | Before | Pod/restart/OOM baseline | Yes | TBD | TBD |
| REL-EV-03 | Before | Quota và Pending | Yes | TBD | TBD |
| REL-EV-04 | Peak | HPA và tổng replica=22 | Yes | TBD | TBD |
| REL-EV-05 | Peak | Storefront/checkout/cart SLO | Yes | TBD | TBD |
| REL-EV-06 | Peak | OOM/restart/Pending/5xx | Yes | TBD | TBD |
| REL-EV-07 | Peak | CPU throttle/memory saturation | Yes | TBD | TBD |
| REL-EV-08 | After | HPA và tổng replica=16 | Yes | TBD | TBD |
| REL-EV-09 | After | Pod health và events | Yes | TBD | TBD |

Completeness rules:

- Có timestamp và timezone.
- Có TEST_ID.
- Query window trùng TEST_START/TEST_END.
- Ảnh dashboard phải nhìn thấy panel title, time range và value.
- Command output phải giữ header và namespace/context liên quan.
- Không dùng evidence của lần test khác.

## 2. Cost Optimization

| ID | Phase | Signal | Bắt buộc | Trạng thái | Path |
|---|---|---|---|---|---|
| COST-EV-01 | Before | Node/NodeClaim inventory | Yes | TBD | TBD |
| COST-EV-02 | Before | Pricing source và timestamp | Yes | TBD | TBD |
| COST-EV-03 | Peak | Node/NodeClaim inventory | Yes | TBD | TBD |
| COST-EV-04 | Test | Locust stats/failures CSV | Yes | TBD | TBD |
| COST-EV-05 | Test | Prometheus successful order query | Yes | TBD | TBD |
| COST-EV-06 | After | Node/NodeClaim inventory | Yes | TBD | TBD |
| COST-EV-07 | After | HPA về 16 | Yes | TBD | TBD |
| COST-EV-08 | Cleanup | NodePool `2m` và annotation đã gỡ | Yes | TBD | TBD |

Không kết luận cost/order không phình khi thiếu một trong các evidence: test window, node price, node timeline hoặc successful order.

## 3. Evidence review

| Check | PASS/FAIL | Reviewer | Ghi chú |
|---|---|---|---|
| Reliability evidence đầy đủ | TBD | CDO-02 | TBD |
| Cost evidence đầy đủ | TBD | CDO-02 | TBD |
| Locust/Prometheus cùng window | TBD | CDO-01/CDO-02 | TBD |
| Deploy/cleanup evidence hợp lệ | TBD | Team Deploy/CDO-02 | TBD |

