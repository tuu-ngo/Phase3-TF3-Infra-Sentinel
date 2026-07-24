# PM-155 — Mandate #19: Throughput Ceiling, Graceful Degradation and Demo Plan

| Field | Value |
|---|---|
| Jira | PM-155, thuộc PM-151 — Mandate #19 Throughput Ceiling |
| Assignee | Tuấn Anh |
| Deadline | **2026-07-22 23:59 Asia/Ho_Chi_Minh** |
| Dependency chain | PM-152 -> PM-153 -> PM-154 -> PM-155 |
| Document state | `INTEGRATION PLAN / EVIDENCE CONTRACT`; không phải runtime proof hoặc Mandate #19 Done |

> PM-155 không tự tạo số before/after và không coi plan là load-shedding chạy thật. Mandate #19 chỉ có thể đóng sau khi PM-152/153/154 đã triển khai, chạy đúng protocol, và PM-155 có raw runtime evidence, rehearsal và ADR ký tên.

## 1. Verdict và dependency contract

| Area | Current plan verdict |
|---|---|
| Overall direction | `CORRECT` |
| PM dependency chain | `DEFINED` |
| Benchmark reproducibility | `BLOCKED UNTIL PM-152 PROTOCOL PASS` |
| Tuning attribution | `BLOCKED UNTIL PM-153 ONE-CHANGE EVIDENCE` |
| Load-shedding demo | `BLOCKED UNTIL PM-154 DEPLOYED/VERIFIED` |
| Mandate closure | `BLOCKED` |

PM-155 nhận các artifact sau, không nhận số viết trong comment:

| Owner/task | Required handoff |
|---|---|
| PM-152 | Locust profile/version, fixed transaction mix, R0/stage schedule, SLO/p99, highest passing stage, reproduced breakpoint, old sustained served RPS, node-set hash/timeline, raw Locust/Prometheus/trace, bottleneck matrix |
| PM-153 | primary/co-bottleneck evidence, one-change iteration log, saturation before/after, tuning diff/image/config revision, correctness reconciliation, new sustained ceiling, RPS/node and same node hash |
| PM-154 | protected cart/checkout journey, shed-first classification, calibrated formula inputs/buckets, rendered Envoy config, enabled/enforced/counter/header evidence, browse 429, checkout SLO, recovery and rollback |
| PM-155 | exact-window before/after comparison, rehearsal log, live overload demo, signed ADR/report and closure checklist |

Thiếu một artifact hoặc artifact chỉ có screenshot/summary: trả task về owner, không suy diễn `PASS`.

## 2. Canonical protocol áp dụng cho mọi task

PM-152, PM-153 và PM-154 phải dùng cùng:

- Locust Mandate 19 profile, version pin, profile SHA và fixed transaction mix;
- warm-up 5 phút, stage 5 phút, offered RPS tăng `ceil(previous * 1.25)`;
- exact-window Prometheus range query và raw Locust CSV;
- SLO: checkout success `>=99%`, browse/cart `>=99.5%`, browse p95 `<1000ms`, checkout p99 `<300ms` theo PM-143; browse p99 phải có value PM/mentor approve trước official run;
- correctness: successful checkout = unique orders = expected payment/Kafka events, duplicate/lost event `=0`;
- node-set hash gồm name + UID + providerID + instance type + AZ, sample mỗi 30 giây;
- load generator ngoài node set under test hoặc chứng minh capacity tách biệt;
- `BASE_SHA`, image/config digests, Argo revision và dependency freeze record.

`old_ceiling` và `new_ceiling` đều là sustained **served RPS trung bình của stage pass**, không phải max instantaneous Grafana, max user hay spike. Breakpoint phải fail trong hai cửa sổ một phút liên tiếp hoặc offered tăng/served plateau kèm saturation signal, rồi được re-run.

Rolling 24h Grafana gauge không được dùng làm breakpoint evidence. Grafana screenshot chỉ là presentation; raw Prometheus/Locust/trace là source of truth.

## 3. Technical gates trước official baseline

### Mandate #16

PM-143 phải chốt p99 budget (checkout hiện có candidate `<300ms>`, browse p99 cần PM/mentor approve). PM-144 và PM-145 phải stable/deployed/validated, hoặc PM owner ghi rõ lý do freeze đã được phê duyệt. Không chạy official PM-152 khi PM-144 còn thay đổi runtime chưa freeze.

### Mandate #17

PM-148 NetworkPolicy phải merge/deploy/soak trước benchmark hoặc được hoãn chính thức. PM-149 RBAC phải freeze trước rehearsal. Không apply policy giữa before/after; telemetry/data-store egress lỗi làm run invalid.

### Mandate #10

PM-127/128 verifyImages/SBOM admission contract và PM-129 dependency pins phải được chốt trước build/promotion image của PM-153/154. Nếu không thể merge trước, freeze exact release digest; không đổi admission/build giữa before và after.

### Mandate #20 và node runtime

PM-160/161 không block chuẩn bị nhưng cấm backup/restore, KMS/IAM destructive test, retention cleanup hoặc snapshot export trong benchmark window. Karpenter scale-up/voluntary disruption phải freeze; NodeClaim, Spot interruption, replacement hoặc node-set hash đổi làm run `INVALID_NODE_SET_CHANGED`.

## 4. Dependency graph và state machine

```text
PM-143 p99 budget + PM-144/145 stable
                    |
                    v
          PM-152 old sustained ceiling
                    |
                    v
          PM-153 one-change tuning/new ceiling
                    |
                    v
          PM-154 calibrated load shedding
                    |
                    v
          PM-155 rehearsal/demo/signed ADR
```

State transitions:

```text
PLANNED -> BASELINE_READY -> PM152_PASS -> PM153_PASS
         -> PM154_SHADOW_PASS -> PM154_ENFORCED_PASS
         -> REHEARSAL_PASS -> ADR_SIGNED -> CLOSURE_READY
```

Rollback về state trước khi gate fail; không chuyển `DONE` từ `PLAN` hoặc một run xanh đơn lẻ.

## 5. Phase 0 — Contract, freeze and PR metadata

Trước official run, PM-155 phải:

1. comment Jira links `blocks/is blocked by` cho PM-152/153/154;
2. record status snapshot với `capturedAt` UTC và nguồn Jira/API, không dùng export cũ không timestamp;
3. ghi owner acceptance của từng artifact và lịch change-freeze/rehearsal;
4. cập nhật PR body mô tả scope docs-only, status `BLOCKED` và evidence required;
5. request formal review từ owner/mentor; CI phải có checks liên quan, không coi Secret scan là implementation evidence;
6. verify branch đã rebase `origin/main` mới nhất trước review và record base SHA.

PR #289 có thể được approve ở tư cách execution plan sau các cập nhật này; merge không đồng nghĩa runtime implementation hoặc Mandate closure.

## 6. Phase 1 — Evidence workspace và dashboard

Không điền số giả. Chuẩn bị:

```text
docs/evidence/mandate-19/
  pm-152/{environment,load-profile,locust,prometheus,nodes,traces,breakpoint-summary}
  pm-153/{baseline,iterations,tuning-decision,new-ceiling,correctness}
  pm-154/{calibration,envoy-config,shadow,enforced,rollback,node-proxy}
  pm-155/{before-after,rehearsal,mentor-demo,closure}
docs/adr/<next>-mandate-19-throughput-ceiling-and-load-shedding.md
docs/runbooks/mandate-19-live-demo.md
```

Dashboard Mandate 19 phải dùng exact test time range và có offered/served RPS, browse/cart/checkout success + p95/p99, HPA Ready/current/max, CPU/throttling/memory/GC, DB pool/connections, Envoy pending/overflow/local-rate counters, queue/cache signals, node-set hash/RPS-node, restarts và recovery. Existing SLO dashboard `[24h]` chỉ để context.

## 7. Phase 2 — PM-152 acceptance

PM-155 chỉ nhận PM-152 khi:

- dedicated Locust profile không AI/flagd mutation, version-pin và fixed mix;
- exact SLO/p99 contract được ghi trước run;
- warm-up/stage/re-run protocol đủ;
- old ceiling là highest passing sustained served RPS;
- breakpoint được tái hiện, earliest bottleneck có metric + trace và co-bottleneck được nêu;
- node-set hash không đổi; load generator không tranh capacity;
- raw Locust/Prometheus/trace và correctness/recovery evidence có đủ.

Thiếu artifact: `PM152_REJECTED_MISSING_EVIDENCE`.

## 8. Phase 3 — PM-153 acceptance

PM-155 chỉ nhận PM-153 khi:

- bottleneck được chứng minh, không chọn trước `product-catalog`/pool/HPA;
- mỗi iteration có một hypothesis/change group, same load protocol và rollback;
- HPA tuning không tạo Pending/NodeClaim hoặc node change; DB pool có arithmetic `pool*max replicas + other services + reserve < max_connections`;
- saturation metric giảm/cải thiện, no SLO/p99 regression;
- new sustained ceiling `>` old ceiling và `RPS/node` tăng;
- correctness reconciliation pass, không duplicate/lost payment/order/Kafka event;
- image/config/Git/Argo revision và raw evidence được lưu.

Nếu `new_ceiling <= old_ceiling`: `PM153_BLOCKED`, không chuyển sang calibration PM-154.

## 9. Phase 4 — PM-154 acceptance

PM-155 chỉ nhận PM-154 khi:

- protected `POST /api/cart` và `POST /api/checkout` không đi qua browse bucket; dependency được pre-seed hoặc route riêng;
- bucket lấy từ PM-153 `new_ceiling`, measured checkout RPS, safety factor/margin và minimum Ready proxy replicas;
- Local Rate Limit per-proxy caveat được ghi và effective cap có evidence;
- shadow mode pass, final `filter_enabled=100%` và `filter_enforced=100%`;
- route names, `429`, `x-techx-load-shed`, `x-envoy-ratelimited`, enabled/ok/rate_limited/enforced counters có raw evidence;
- overload stage duy trì đủ, browse 429 có chủ đích, checkout success/p99 giữ SLO, no unexpected 5xx/timeout/OOM/restart/node change;
- hạ tải xong hệ phục hồi và rollback được rehearsal;
- Envoy admin không public.

Thiếu route/counter/header hoặc 429 do route mismatch: `PM154_REJECTED_INVALID_SHEDDING`.

## 10. Phase 5 — Change freeze and preflight

Freeze checkout, frontend, frontend-proxy, cart, product-catalog, product-reviews, recommendation, payment, shipping, HPA/resources, Karpenter/NodePools, NetworkPolicy, RBAC, observability, RDS/ElastiCache/MSK, CI/admission và flagd. Chỉ approved rehearsal blocker fix hoặc emergency rollback được phép.

Capture:

```bash
git rev-parse HEAD
git show -s --format='%H %cI' HEAD
kubectl get nodes -o wide
kubectl get hpa -n techx-tf3
kubectl get pods -n techx-tf3 -o wide
kubectl get nodepool,nodeclaim
kubectl get networkpolicy -n techx-tf3
kubectl get clusterpolicy
```

Preflight fails on wrong context/account, stale base SHA, missing node-set hash, pending pod, unready proxy, missing dashboard query, load-generator saturation or active backup/restore/perf benchmark interference.

## 11. Phase 6 — Before/after comparison

| Metric | Before | After | Acceptance |
|---|---:|---:|---|
| Sustained served RPS | raw PM-152 | raw PM-153 | After `>` before |
| Offered RPS | exact stage | exact stage | Same mix/duration |
| Node-set hash | SHA | SHA | Equal |
| Node count / RPS per node | raw | raw | RPS/node increases |
| Browse/cart success + p95/p99 | raw | raw | SLO pass |
| Checkout success + p99 | raw | raw | >=99%, approved budget |
| Primary saturation metric | raw | raw | Improves or new owner recorded |
| Correctness reconciliation | raw | raw | no duplicates/lost events |
| Shedding 429 | n/a | raw PM-154 | Intentional browse only |
| Recovery | raw | raw | Returns to normal |

Fail comparison if traffic mix, stage duration, node set, SLO, release digest or freeze state differs; if only a max spike is shown; or if one run has shedding and the other does not.

## 12. Phase 7 — Rehearsal and live demo

1. Verify freeze, account/context, node-set hash, proxy replicas, dashboard and trace export.
2. Start protected checkout stream at measured RPS.
3. Offer browse above calibrated cap for a sustained stage.
4. Show browse 429 with route/header/counter; show checkout journey success/p99 and no browse bucket rejection on cart/checkout.
5. Show node/proxy/HPA health and unchanged node hash.
6. Lower load; show 429 recovery, checkout stability, pod readiness and datastore health.
7. Save raw artifacts immediately; do not transcribe values from screenshot later.

Escalation map: missing breakpoint -> PM-152; unclear saturation/new ceiling -> PM-153; route/429/header/counter failure -> PM-154; RBAC/NetworkPolicy -> PM-149/148; admission/build/promotion -> PM-127/128/129.

## 13. Phase 8 — ADR, report and DoD

ADR must contain: decision owner/role/date, exact old/new sustained RPS, offered/served protocol, node-set hash, primary/co-bottleneck metric and trace, one-change tuning history, RPS/node, Envoy policy/formula/per-proxy trade-off, intentional 429 versus unexpected errors, correctness reconciliation, cost/operational trade-off, rollback, reviewers and mentor acceptance.

PM-155 and Mandate #19 remain `BLOCKED` until all are true:

- PM-152/153/154 acceptance gates pass with raw evidence;
- old/new ceiling and RPS/node use same protocol and unchanged node hash;
- dashboard uses exact test windows and raw Prometheus/Locust/trace artifacts are committed;
- browse 429 is intentional; protected cart/checkout stays within SLO; no outage/OOM/restart;
- recovery and rollback rehearsal pass;
- correctness has zero duplicate/lost order/payment/event;
- ADR is signed, report is reviewed, Jira status is refreshed with timestamp;
- PR body, formal review and checks are present;
- no unowned Critical/High gap remains.

Until then the official verdict is:

```text
Plan can be reviewed:        YES, after these document changes
Benchmark officially ready:  NO, until PM-152 gates pass
Mentor demo ready:           NO, until PM-154 runtime evidence passes
PM-155 Done:                 NO
Mandate #19 Done:            NO — BLOCKED
```
