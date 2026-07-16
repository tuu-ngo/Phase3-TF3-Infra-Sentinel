# Kế hoạch cải thiện hệ thống — 3 trụ (Reliability · Cost · Operational Excellence)

**Ngày lập:** 12/07/2026 · **Người lập:** CDO02
**Nguồn:** tổng hợp từ `docs/backlog/cdo02-reliability-cost-backlog.md` (REL-01..16, COST-01..07),
ADR 0001 (nâng EKS), review PR #35 (GitOps merge), và các phát hiện runtime tuần 1.
**Cập nhật lớn:** PR #35 đã merge → **ArgoCD/GitOps là mô hình chính thức**, LimitRange +
auto-sync/selfHeal đang LIVE → phát sinh việc mới ở trụ Operational Excellence.

Dùng cho Ops Review hằng tuần + theo dõi tiến độ. Đánh dấu `[x]` khi xong.

---

## 🔴 RELIABILITY

### P0 — làm ngay
- [ ] **REL-01** — replicas ≥2 + PDB nhóm checkout (PR #34 chờ merge). Nền tảng để sống sót node drain + upgrade EKS.
- [ ] **REL-02 + REL-03** — sửa health check giả → check dependency thật, rồi thêm readiness/liveness probe. Vá gốc INC-3.
- [ ] **REL-09 + REL-16** — Kafka ack (`WaitForAll`) + accounting manual-commit + dead-letter. Kafka đã OOM thật (near-miss mất đơn hàng). Nặng nhất về dữ liệu tài chính.
- [ ] **REL-04** — rollback/refund trong `checkout` khi ship lỗi sau charge.

### P1 — trong tuần
- [ ] **REL-05** — connection pool Postgres (`product-catalog`/`product-reviews`). Vá gốc INC-1.
- [ ] **REL-14** — điều tra crash `product-catalog` (restart 3, memory 20Mi, traffic cao nhất).
- [ ] **REL-10** — persistence `valkey-cart` (+ accepted-risk ADR cho Postgres/Kafka). **Cấp hơn giờ vì `prune` ArgoCD có thể xóa nhầm pod datastore.**
- [ ] **REL-13** — vá gốc Grafana OOM (tăng memory bền vững).

### P2 — nếu còn giờ
- [ ] **REL-06** (load test memory) · **REL-11** (currency validate) · **REL-12** (quote validate).

---

## 💰 COST OPTIMIZATION

### P0 — cắt phí đo được ngay
- [ ] **Nâng EKS 1.32→1.34** (ADR 0001) — 1.32 đang trả phí extended ~6×. Làm **sau** REL-01.

### P1
- [ ] **COST-01** — viết lại ECR lifecycle policy đúng (dọn nợ tự gây).
- [ ] **COST-02** — Cluster Autoscaler thật (IRSA đã sẵn) — hiện trả tiền 3 node 24/7.

### P2
- [ ] **COST-03** — Spot cho workload chịu gián đoạn (chỉ sau REL-01).
- [ ] **COST-04** — right-size instance sau khi có số liệu CPU thật.
- [ ] **COST-05** — điều tra `load-generator` OOM ở 1500Mi (**KHÔNG giảm** — đã đính chính).

---

## ⚙️ OPERATIONAL EXCELLENCE (nhiều việc MỚI từ GitOps merge)

### P0 — hệ quả trực tiếp của PR #35
- [ ] **🔴 Verify LimitRange 200m CPU không bóp nghẹt gateway** — giờ live, mỗi pod restart nhận CPU limit 200m. `product-catalog`/`frontend-proxy`/`frontend` traffic cao có thể bị throttle → đe dọa SLO browse p95 <1s. Đo CPU throttle qua Prometheus; nếu có, đặt CPU explicit per-service.
- [ ] **Đổi `prune: true` → `prune: false`** cho app `techx-corp` (rủi ro xóa nhầm datastore 0 PVC).
- [ ] **Áp dụng runbook incident + ArgoCD** ([`docs/runbooks/incident-response-with-argocd.md`](../runbooks/incident-response-with-argocd.md)) — team đọc + drill escape hatch.

### P1
- [ ] **Viết ADR chính thức cho mô hình GitOps** — đang live mà chưa có ADR (thiếu Auditability). Kèm quyết định selfHeal/prune.
- [ ] **REL-15** — alerting OOM/restart/readiness (mọi phát hiện gần đây đều thủ công → MTTR kém).
- [ ] **🔒 Rotate flagd sync token** — đang plaintext trong Helm release cũ (`helm get values` đọc được).
- [ ] **Dựng AWS Budget alert** — theo dõi trần $300/tuần (BUDGET.md nhắc "nên làm sớm").

### P2
- [ ] `ignoreDifferences` cho field runtime-mutable (chuẩn bị HPA).
- [ ] Theo dõi `mandates/` mỗi ngày (hiện trống).

---

## Thứ tự thực thi thực tế (chuỗi phụ thuộc)

```
REL-01 (replicas+PDB) → verify LimitRange + prune:false → REL-02/03 (health+probe)
→ REL-09/16 (Kafka) → REL-05/14 (Postgres) → REL-15 (alert)
→ [khi ổn định] nâng EKS 1.34 → COST-02 (autoscaler) → COST-03 (spot)
```

## Ghi chú phối hợp
- Nhiều mục Performance/Security (P07/P08/P11/P12/P15/P16/P18/P22) đã bàn giao **CDO01** qua meeting liên team — không thuộc kế hoạch này, chỉ tham chiếu.
- Mọi thay đổi app giờ đi qua **git/ArgoCD** (không helm tay) — xem runbook.
- Migrate datastore sang managed service (RDS/ElastiCache/MSK): xem phân tích riêng, **chờ mandate BTC** trước khi đầu tư lớn (REL-08).
