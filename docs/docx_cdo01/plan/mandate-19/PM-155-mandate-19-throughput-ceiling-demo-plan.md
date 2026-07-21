# PM-155 — Mandate #19: Demo RPS đỉnh trước-sau, requests-per-node, bottleneck và xuống mềm

**Jira chính:** PM-155
**Epic:** PM-151 — Mandate #19 Throughput Ceiling
**Assignee:** Tuấn Anh
**Deadline:** 2026-07-22 00:00
**Nguồn:** Jira export do người dùng cung cấp và trạng thái kỹ thuật repo.

> PM-155 là task tích hợp cuối. Không tự tạo số before/after, không xem tài liệu là thay thế load-shedding chạy thật, và không báo `Done` khi thiếu dependency/evidence runtime.

## 1. Epic status và hard blockers

| Key | Status tại export | Assignee | Vai trò |
|---|---|---|---|
| PM-151 | To Do | Chưa gán | Epic Throughput Ceiling |
| PM-152 | To Do | hoàng công trí dũng | Breakpoint/trần cũ |
| PM-153 | To Do | hoàng công trí dũng | Nới bottleneck, nâng trần cùng node set |
| PM-154 | To Do | Long Trần | Load-shedding/rate-limit bảo vệ checkout |
| PM-155 | In Progress | Tuấn Anh | Tích hợp, rehearsal, demo mentor, ADR/report |

```text
PM-152 breakpoint → PM-153 tuning/new ceiling → PM-154 calibrated load-shedding → PM-155 demo/ADR
```

PM-155 có thể chuẩn bị dashboard/runbook/template ngay; không thể hoàn tất DoD trước PM-152/153/154.

| Input owner | Artifact contract bắt buộc cho PM-155 |
|---|---|
| PM-152 | protocol, traffic mix, offered/served RPS từng stage, SLO, breakpoint tái hiện, old ceiling, node set, Locust raw, Grafana window, saturation ban đầu |
| PM-153 | bottleneck/service-resource, saturation metric, trace, tuning diff, image/config revision, correctness, post-tuning test, new ceiling, same node set, RPS/node before/after |
| PM-154 | browse/checkout classification, deployed policy, counter/header, browse 429 chủ đích, bucket checkout tách biệt, overload test, rollback, same node set |

## 2. Technical prerequisites và freeze rules

### Mandate #16

PM-143 (SLO p95/p99), PM-144 (song song hóa `checkout.prepOrderItems`) và PM-145 (validation stability/cost) là prerequisite đề xuất cho PM-152:

```text
PM-143 Done + PM-144 merged/deployed + PM-145 pass + runtime freeze → official PM-152 baseline
```

PM-146 demo/ADR không là hard technical blocker nếu runtime đã ổn định. **Không chạy official baseline khi PM-144 còn In Progress.**

### Mandate #17

PM-148 NetworkPolicy có thể làm bẩn benchmark qua telemetry, load-generator hoặc data-store egress. Chọn đúng một:

```text
A. PM-148 merge, deploy, smoke-test, soak trước PM-152 (khuyến nghị)
B. Hoãn apply PM-148 tới sau PM-155
```

Không apply policy giữa PM-152 baseline, PM-153 tuned test, PM-154 overload. PM-149 RBAC phải Done/freeze trước rehearsal để tránh `Forbidden`; PM-150 demo/ADR không block nếu runtime đã stable.

### Mandate #10

Trước deploy image PM-153/154 phải chốt Jira overlap PM-127/128: verifyImages có Enforce signature không, SBOM attestation có bắt buộc không, policy identity nào được nhận, và image mới có pass admission không.

Trình tự khuyến nghị:

```text
PM-127 contract chốt → PM-129 merge dependency pins → PM-153/154 rebase
→ build + scan + sign + SBOM → digest promotion → official benchmark
```

Nếu PM-129 để sau, phải freeze và không merge giữa before/after. PM-132 không là dependency kỹ thuật PM-155.

### Mandate #20 và nền runtime

PM-160/161 không block PM-155, nhưng cấm snapshot/backup/restore, KMS/IAM destructive test, retention cleanup hoặc export trong benchmark window. Mandate #13 đã Done là nền tốt, nhưng node set/Karpenter phải cố định. PM-121 không block trực tiếp.

## 3. Dependency graph chính thức

```text
MANDATE #16: PM-143 + PM-144 → PM-145 validation
                                     ↓
MANDATE #19:                     PM-152 breakpoint
                                     ↓
                                  PM-153 bottleneck/new ceiling
                                     ↓
                                  PM-154 calibrated shedding
                                     ↓
                                  PM-155 rehearsal/demo/ADR
```

Gate song song: PM-148 deploy+soak hoặc hoãn; PM-149 Done/freeze trước rehearsal; PM-127/128 admission chốt; PM-129 merge trước build hoặc freeze; PM-160/161 không chạy trong test window.

## Phase 0 — Xác nhận với PM

Tạo Jira `blocks/is blocked by` và comment:

```text
Hard blockers PM-155: PM-152, PM-153, PM-154.
Technical gates: PM-143/144/145 trước PM-152; PM-148 deploy+soak hoặc hoãn;
PM-149 freeze trước rehearsal; PM-127/128 xác nhận admission; PM-129 merge trước
image build hoặc freeze; PM-160/161 không chạy trong benchmark window.
```

**Output:** links, owner xác nhận artifact contract, lịch freeze, rehearsal và mentor demo.

## Phase 1 — Chuẩn bị không bị block

Tạo các artifact (không điền số giả):

```text
docs/mandate-19-throughput-report.md
docs/adr/<next>-mandate-19-throughput-ceiling-and-load-shedding.md
docs/runbooks/mandate-19-live-demo.md
```

Report gồm environment, SLO, protocol, old/new ceiling, bottleneck, tuning, RPS/node, shedding, correctness, limitations, DoD matrix.

Dashboard tối thiểu: offered/served RPS; browse success/p95/p99; checkout success/p99; node count/RPS-node; saturation; browse 429; shedding counter; pod restart/Ready.

Evidence collector phải lưu exact time range, node names/UID/providerID, HPA, replicas, image digests, Git SHA, Locust CSV, Prometheus output, screenshots và trace IDs.

## Phase 2 — Acceptance PM-152

- [ ] PM-152 Done, breakpoint tái hiện, highest passing stage và old ceiling.
- [ ] Có SLO, offered/served RPS, node set, raw Locust và Grafana window.
- [ ] Không PM-144/148 deployment chen giữa; load generator không là bottleneck.

Thiếu artifact: trả về PM-152, không suy diễn `RPS đỉnh trước`.

## Phase 3 — Acceptance PM-153

- [ ] PM-153 Done; bottleneck là saturation có trace/metric, không chỉ "chậm".
- [ ] Tuning gắn đúng nguyên nhân; correctness và image/config revision rõ.
- [ ] New ceiling dùng cùng protocol, SLO, node set; RPS/node tăng.
- [ ] Không thêm node, không nới SLO.

New ceiling không tăng nghĩa là PM-153 chưa đạt DoD và PM-155 vẫn blocked.

## Phase 4 — Acceptance PM-154

- [ ] PM-154 Done; browse/checkout route priority và bucket tách biệt.
- [ ] Browse 429 chủ đích, có policy counter/header.
- [ ] Offered load vượt new ceiling; checkout success >=99%; không outage toàn hệ.
- [ ] Node set không đổi, có rollback.

Rate limit chỉ calibrate sau `new ceiling` của PM-153.

## Phase 5 — Change freeze

Freeze checkout, frontend, frontend-proxy, cart, product-catalog, recommendation, payment, shipping, HPA, resources, Karpenter, NetworkPolicy, RBAC, observability, RDS/ElastiCache/MSK, CI/admission và flagd. Chỉ cho phép approved rehearsal blocker fix hoặc emergency rollback.

```bash
git rev-parse HEAD
kubectl get nodes -o wide
kubectl get hpa -n techx-tf3
kubectl get pods -n techx-tf3 -o wide
kubectl get networkpolicy -n techx-tf3
kubectl get clusterpolicy
```

## Phase 6 — So sánh before/after

| Metric | Before | After | Điều kiện |
|---|---:|---:|---|
| Sustained SLO RPS | | | Cùng protocol/SLO |
| Offered RPS | | | Cùng traffic mix/duration |
| Node count | | | Không đổi |
| Node-set hash | | | Same |
| RPS/node | | | Phải tăng |
| Browse success/p95/p99 | | | |
| Checkout success/p99 | | | Success >=99% overload |
| Bottleneck saturation | | | Metric + trace |

Fail comparison nếu khác traffic mix, duration, node set/SLO; có deployment PM-144/148/129 chen giữa không ghi nhận; chỉ một run có shedding; hoặc dùng max spike thay sustained stage.

## Phase 7 — Rehearsal và escalation

1. Preflight, mở dashboard/node watcher.
2. Chạy protected checkout stream.
3. Tăng browse vượt trần.
4. Chứng minh browse 429, checkout giữ SLO, node không đổi.
5. Hạ tải, xác nhận recovery và lưu evidence.

| Lỗi | Trả về |
|---|---|
| Không breakpoint | PM-152 |
| Bottleneck/new ceiling không rõ | PM-153 |
| Checkout bị rate-limit, không 429/counter | PM-154 |
| RBAC Forbidden | PM-149 |
| NetworkPolicy chặn telemetry/data store | PM-148 |
| Admission/build/promote fail | PM-127/128/129 hoặc release owner |

## Phase 8 — Demo mentor

1. Before/after: old/new ceiling, node count, RPS/node, SLO.
2. Bottleneck: saturation metric, trace, tuning và after metric.
3. Live overload: offered RPS, browse 429, checkout success/p99, node/pod health, recovery.
4. ADR: old/new ceiling, bottleneck, solution, shedding, trade-off, rollback.

## Phase 9 — Final ADR/report và DoD

Chỉ điền số thật sau rehearsal. ADR bắt buộc có decision owner, name, role, date, Git commit, reviewers, mentor acceptance; không placeholder bản nộp.

- [ ] PM-152/153/154 Done, artifact đủ và new ceiling tăng.
- [ ] PM-143/144/145 stable; PM-148 deploy+soak hoặc hoãn; PM-149 không gây Forbidden.
- [ ] PM-127/128 admission rõ; PM-129 không chen release state; PM-160/161 không interference.
- [ ] Same node set, RPS/node tăng, saturation metric + trace.
- [ ] Browse 429 chủ đích, checkout >=99%, không outage.
- [ ] Rehearsal pass, ADR ký, report/evidence committed, không thay flagd, không còn gap chưa ghi rõ.

## PM confirmation message

```text
PM-155 là task tích hợp cuối PM-151, hard-block bởi PM-152/153/154. Đề xuất gate
PM-143/144/145 trước PM-152; PM-148 deploy+soak hoặc hoãn; chốt PM-127/128;
PM-129 merge trước build hoặc freeze; không chạy backup/restore PM-160/161 trong
benchmark window. Trong lúc chờ, em chuẩn bị dashboard, collector, runbook và
template ADR/report. PM-155 chỉ Done sau artifact đủ, rehearsal pass và mentor demo.
Nhờ PM xác nhận dependency links và change-freeze.
```
