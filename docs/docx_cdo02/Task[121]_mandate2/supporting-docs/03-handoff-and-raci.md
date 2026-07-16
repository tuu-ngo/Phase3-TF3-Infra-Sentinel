# Supporting 03 — Handoff and RACI

## 1. Reliability

| Activity | CDO-02 | CDO-01 | Team Deploy |
|---|---|---|---|
| Capacity analysis | A/R | I | C |
| Solution proposal | A/R | I | C |
| Manifest change/deploy | C | I | A/R |
| Live-state validation | A/R | I | C |
| Start/stop/abort load | C | A/R | I |
| HPA/OOM/Pending/5xx monitoring | A/R | I | C |
| Reliability verdict | A/R | C | C |

### 1.1 Team Deploy handoff

CDO-02 cung cấp:

- Gap/risk ID.
- Current state và expected state.
- Impact/SLO risk.
- Acceptance criteria.
- Deadline trước test.

Team Deploy trả:

- PR/commit.
- Rendered manifest hoặc diff.
- GitOps sync/health status.
- Live resource output.
- Rollback reference.

### 1.2 Abort handoff

`(Bàn giao CDO-01)` gồm:

- Test ID.
- ABORT_TIMESTAMP.
- Signal và threshold bị vi phạm.
- Yêu cầu dừng tải.
- Yêu cầu partial Locust export.

## 2. Cost Optimization

| Activity | CDO-02 | CDO-01 | Team Deploy |
|---|---|---|---|
| Node/cost baseline | A/R | I | C |
| Successful order source | C | A/R | I |
| Locust/Prometheus reconciliation | A/R | R | I |
| Cost/hour/window/order calculation | A/R | C | I |
| HPA/node scale-down validation | A/R | I | C |
| Karpenter cleanup deploy | C | I | A/R |
| Cost verdict | A/R | C | C |

### 2.1 Post-test cleanup handoff

Điều kiện mở handoff:

- CDO-01 xác nhận tải đã dừng.
- CDO-02 xác nhận HPA về 16.
- Không có rollout/recovery đang chạy.

`(Bàn giao Team Deploy)`:

- Đặt `consolidateAfter=2m`.
- Gỡ `do-not-disrupt` khỏi 7 component.
- Merge/sync GitOps.
- Trả live NodePool, pod annotation và application health evidence.

CDO-02 xác nhận hiệu lực và cập nhật Cost verdict.

## 3. Handoff log

| ID | Trụ cột | From | To | Nội dung | Due | Status | Evidence |
|---|---|---|---|---|---|---|---|
| M02-HO-01 | Reliability | CDO-02 | Team Deploy | TBD | TBD | TBD | TBD |
| M02-HO-02 | Reliability/Cost | CDO-02 | CDO-01 | TBD | TBD | TBD | TBD |
| M02-HO-03 | Cost | CDO-02 | Team Deploy | TBD | TBD | TBD | TBD |

RACI: `R=Responsible`, `A=Accountable`, `C=Consulted`, `I=Informed`.

