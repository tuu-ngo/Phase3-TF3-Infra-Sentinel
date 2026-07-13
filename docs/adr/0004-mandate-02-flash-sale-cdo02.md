# ADR 0004 — Mandate #2 (flash sale trong ngân sách): phần CDO02 (Cost + Reliability + Ops)

**Ngày:** 12/07/2026
**Người quyết định (ký):** CDO02 (Reliability + Cost Optimization)
**Directive:** [`mandates/MANDATE-02-scale-under-budget.md`](../../mandates/MANDATE-02-scale-under-budget.md) — hạn **14/07/2026**
**Trạng thái:** 🟡 Đã thiết kế + chuẩn bị — **chờ AWS mở account để deploy + chạy load test**
**Phạm vi ADR này:** **phần CDO02** = Cost Optimization + Reliability + Operational Excellence.
Tối ưu độ trễ/khử bottleneck tầng perf là **Performance Efficiency → CDO01**.

---

## Bối cảnh

Flash sale: **200 user đồng thời (qua load-generator), giữ 15 phút**, phải giữ SLO (checkout ≥99%,
browse/cart ≥99.5%, storefront p95 <1s) **mà không tăng ngân sách** (~$300/tuần). Cost **trên mỗi
đơn/request** không được phình. Co lên rồi phải co xuống.

Tải ×nhiều lần thường ngày dồn vào **browse/search + checkout**. Baseline hiện tại: mọi service
`replicas: 1` (đã vá nhóm checkout lên 2 qua REL-01), **không có HPA, không có Cluster Autoscaler
đang chạy, không có metrics-server** (bị gỡ trước đó). Nghĩa là hiện hệ thống **không tự co giãn** —
sẽ bão hòa dưới 200 user.

## Quyết định (phần CDO02)

Gánh tải bằng **co giãn tạm thời rồi trả về**, không thêm cost cố định:

1. **metrics-server** (nền tảng bắt buộc) — HPA + `kubectl top` cần metric CPU/mem. Cài qua ArgoCD
   Application (`gitops/apps/metrics-server-app.yaml`).
2. **HPA cho hot path browse+checkout** (`gitops/infrastructure/hpa-hotpath.yaml`) — `minReplicas: 2`
   (khớp REL-01), `maxReplicas: 5`, target **CPU 70%**. Pod **co lên** khi tải, **co xuống** sau đỉnh.
3. **Cluster Autoscaler** (`gitops/apps/cluster-autoscaler-app.yaml`) — IRSA đã sẵn
   (`arn:aws:iam::012619468490:role/techx-corp-tf3-cluster-autoscaler`). Node group ASG min=3/max=6:
   thêm node **tạm** lúc đỉnh, cấu hình **scale-down aggressive** (`scale-down-unneeded-time: 2m`) để
   trả node về 3 ngay sau đỉnh → cost cố định **không neo ở đỉnh**.
4. **Khử bottleneck dữ liệu dưới tải** (tận dụng PR đã có): REL-05 connection pool (PR #43) chống cạn
   Postgres khi 200 user dồn vào; REL-09 Kafka ack (PR #45) chống mất đơn khi queue đầy; REL-01
   replicas + PDB giữ availability.

## Đánh đổi đã cân (Perf ⇄ Cost — trọng tâm mandate chấm)

- **Node tạm tăng 3→(tối đa)6 trong 15 phút test** → cost **tuyệt đối** tăng nhẹ trong cửa sổ test,
  nhưng **cost/request KHÔNG phình** (thêm capacity đúng lúc cần, trả lại ngay). Scale-down aggressive
  đảm bảo không neo tiền ở đỉnh. Đây là đánh đổi đúng: gánh tải mà vẫn gọn chi phí.
- **HPA target 70% CPU** — cân giữa phản ứng kịp (không để bão hòa → vỡ SLO) và không scale thừa
  (tốn tiền). Có thể tinh chỉnh sau lần test đầu.
- **maxReplicas: 5** — trần để không scale vô hạn vượt quota/ngân sách; đủ cho 200 user ở quy mô này.
- **Cân nhắc rồi loại:** tăng cứng node/replicas cố định để "chắc chắn gánh nổi" — **loại**, vì đó là
  "quăng thêm tài nguyên" mandate cấm và phình cost 24/7.
- **Phụ thuộc CPU requests:** HPA tính % trên CPU request. LimitRange (CDO01) đang set default
  `requests.cpu: 100m`. 100m khá thấp → HPA có thể nhạy; sẽ tinh chỉnh request/target sau lần test đo
  thật (phối hợp CDO01 ở tầng perf).

## Ràng buộc đã tôn trọng
- **Giữ SLO suốt test** — HPA + PDB + replicas giữ availability; connection pool/Kafka ack giữ đúng đơn.
- **Trong ngân sách** — co lên tạm, co xuống ngay; không thêm cost cố định.
- **Storefront public, ops private** (Mandate #1) — không đụng.
- **flagd KHÔNG đụng.**

## Bằng chứng hoàn thành (evidence)
Chạy load test ở mục tiêu và nộp:
1. **SLO giữ:** dashboard Grafana trong 15 phút @200 user — checkout ≥99%, browse/cart ≥99.5%, p95 <1s.
2. **Cost trong trần:** cost trước/sau (AWS Cost Explorer) + **cost/đơn** không tăng so với baseline.
3. **Co lên → co xuống:** `kubectl get hpa` + số node trước/trong/sau — pod & node trở về mức thường
   sau đỉnh (bằng chứng không neo tài nguyên).
4. Cho mentor cách chạy lại (runbook `docs/runbooks/flash-sale-load-test.md`).

## Rollback plan
- HPA/autoscaler gây bất ổn → `git revert` các manifest → ArgoCD prune (gỡ HPA/CA) → về baseline replicas cố định. Phát hiện qua Grafana SLO tụt trong test → dừng test, revert.
- metrics-server độc lập, gỡ không ảnh hưởng workload.

## Trạng thái thực thi
- [ ] Deploy metrics-server (ArgoCD app) — chờ account mở
- [ ] Deploy HPA hot path + Cluster Autoscaler — chờ account mở
- [ ] Chạy load test 200 user/15 phút, đo SLO + cost
- [ ] Xác nhận co xuống sau đỉnh; nộp evidence

---
*Ký: CDO02. Phối hợp CDO01 (Performance Efficiency — tối ưu latency/bottleneck tầng perf). Deadline
14/07 chịu rủi ro do account hold (đã escalate mentor) — sẵn sàng deploy + test tức thì khi account về.*
