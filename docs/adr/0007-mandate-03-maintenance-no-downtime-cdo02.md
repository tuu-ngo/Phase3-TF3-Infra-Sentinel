# ADR 0007 — Mandate #3 (bảo trì không downtime): phần CDO02 (Reliability)

**Ngày:** 15/07/2026
**Người quyết định (ký):** CDO02 (Reliability + Cost Optimization)
**Directive:** [`mandates/MANDATE-03-maintenance-no-downtime.md`](../../mandates/MANDATE-03-maintenance-no-downtime.md) — hạn **16/07/2026**
**Trạng thái:** 🟢 Đã triển khai app tier (PR #112, #114 đã merge) — **chờ chạy demo drain node trước mentor**
**Trụ:** Reliability (chính) · chạm Performance Efficiency (gọn trong ngân sách) + Auditability (ADR này)

---

## Bối cảnh

Directive #3: drain node / rolling-restart **giữa giờ có khách**, luồng browse → cart → checkout
phải **giữ SLO** (checkout ≥99%, browse/cart ≥99.5%, storefront p95 <1s), khách không rớt request.
3 yêu cầu: (1) không downtime khi bảo trì, (2) không SPOF luồng ra tiền, (3) pod chưa ready không
nhận traffic. Ràng buộc: trong ngân sách (~$300/tuần), **"đừng chỉ nhân đôi mọi thứ cho chắc"**,
không đụng flagd, ops vẫn riêng tư.

## Hiện trạng đã audit (bằng chứng, không suy đoán)

Đọc trực tiếp `deploy/values-prod.yaml` + code service:
- 10 service revenue đã có `replicas: 2` + PDB, nhưng **chỉ `checkout` có `topologySpreadConstraints`**
  → 9 service còn lại: 2 replica có thể nằm **chung 1 node** → drain node đó = mất cả service dù có PDB.
- **Không service nào có graceful shutdown** (`preStop`/`terminationGracePeriodSeconds`) → drain/rollout
  cắt request đang xử lý dở (race giữa SIGTERM và gỡ endpoint).
- Datastore (postgres/valkey/kafka): single-replica + RWO PVC + `Recreate`. postgres+valkey ghim vào
  **1 node stateful duy nhất** (`stateful_1a`, `min=max=desired=1`) → drain node đó = mất browse+cart.

## Quyết định

### 1. App tier — drain-safe thật (PR #112 + #114, $0 chi phí cố định)
- **topologySpread cho cả 10 service revenue**: zone `DoNotSchedule` (hard) ép 2 replica ra 2 AZ khác
  nhau → **luôn ở 2 node khác nhau** → drain 1 node luôn còn ≥1 replica ready. hostname `ScheduleAnyway`
  (soft) cho HPA scale-up không kẹt lịch. (Pattern đã chứng minh ở checkout.)
- **`strategy: RollingUpdate maxUnavailable:0 / maxSurge:1`**: rollout không bao giờ tụt dưới số replica
  mong muốn (thêm-1-trước-khi-bỏ-1).
- **Graceful shutdown**: `preStop sleep 5s` (giữ pod phục vụ sau khi gỡ khỏi endpoint, tránh reset) +
  `terminationGracePeriodSeconds: 30` (25s cho in-flight hoàn tất sau SIGTERM). Dùng native `sleep`
  handler (GA k8s 1.30, không cần shell → chạy cả container distroless). Cần bổ sung render 2 field này
  vào chart template (`_objects.tpl`) + schema (đều guarded, service không set = không ảnh hưởng).
- **readinessProbe**: đã có sẵn trên toàn bộ service revenue (checkout/product-catalog gRPC, còn lại
  tcpSocket) → pod chưa ready không vào Service endpoints (yêu cầu #3).

### 2. Service phụ trợ — GIỮ 1 replica (không nhân đôi, đúng ràng buộc mandate)
Verify code: `ad`/`recommendation` (`Ad.provider.tsx` dùng `useQuery` default `[]`) và `image-provider`
(ảnh 404 vẫn load trang) **degrade gọn** khi chết — không chặn mua hàng. `email` non-fatal trong
checkout (`main.go` chỉ `logger.Warn`). `accounting`/`fraud-detection` là Kafka consumer **async** (sau
checkout, không trên luồng đồng bộ). `llm` mock. → Nhân đôi 7 service này **không cứu request khách nào**
khi drain, mà `accounting`/`fraud` nhân đôi còn thêm rủi ro rebalance consumer group. **Loại — đúng tinh
thần "đừng nhân đôi mọi thứ".**

### 3. Datastore — chấp nhận residual risk có kiểm soát ($0)
Single-replica RWO **không thể** sống sót khi chính node của nó bị drain (cửa sổ detach/reattach PVC
vài chục giây), bất kể số node. Fix thật = replication (RDS/ElastiCache/MSK) → ngoài ngân sách + rủi
ro cao trước hạn (xem ADR 0002). Quyết định:
- Giữ datastore trên node `stateful_1a` chuyên dụng (on-demand, tainted, không bị Karpenter đụng).
- **Demo drain 1 node APP tier** để chứng minh luồng ra tiền zero-impact — không drain node stateful.
- **Bảo trì chính node stateful KHÔNG bị né** — có quy trình planned-failover có kiểm soát:
  [`docs/runbooks/stateful-node-planned-maintenance.md`](../runbooks/stateful-node-planned-maintenance.md).
  Nói thẳng con số: downtime **~30-60s/datastore** (detach/reattach PVC + restart), trong cửa sổ off-peak,
  giảm thiểu bằng client retry. Đây là bản chất single-replica RWO, không phải bỏ sót — zero-downtime tầng
  data cần replication (RDS Multi-AZ / ElastiCache / operator), là **quyết định ngân sách có ý thức**, không
  phải "không biết cách". Đo downtime thật trong dry-run/demo, báo cáo số thật vào ADR này.
- Ghi nhận đường HA thật là roadmap (RDS/ElastiCache) khi có ngân sách lớn hơn.

## Đánh đổi đã cân
- **topologySpread zone hard (`DoNotSchedule`)** đảm bảo tách node nhưng nếu 1 AZ cạn node lúc rollout,
  maxSurge pod chờ (không tụt availability nhờ `maxUnavailable:0`) → **fail-safe**, không ảnh hưởng khách.
- **preStop 5s + grace 30s**: thêm ~5s vào thời gian terminate mỗi pod — chấp nhận được, đổi lấy 0 request
  rớt lúc drain/rollout.
- **Datastore không HA**: residual risk có ý thức, đã ghi rõ + có đường roadmap, thay vì tiêu tiền/thời
  gian gấp cho giải pháp nửa vời (2 node stateful vẫn không chống được blip single-replica).

## Giới hạn đã biết (nói thẳng với mentor, không giấu)
- **frontend-proxy là ALB target** (`target-type=ip`): endpoint nội bộ propagate nhanh nhưng ALB
  deregistration chậm hơn → preStop riêng cho tier này dài hơn (20s) + `deregistration_delay=30s` trên
  target group (xem PR ALB graceful drain). Backend gRPC giữ preStop 5s.
- **readinessProbe theo bản chất service (đính chính so với bản đầu):** service **có dependency stateful**
  (`product-catalog`/`product-reviews` → Postgres, `checkout` → dependency) đã dùng **gRPC readiness →
  Health service dependency-aware** (poll `db.Ping`/kiểm dependency, flip `NOT_SERVING` khi hỏng) —
  REL-02 đã làm + deployed (commit `8ce45af`, `e6a3717`; image `6a3fe95`/`7527509`). Service **stateless**
  (currency/ad/payment/frontend/... → không có DB/Kafka/Redis ngoài) dùng `tcpSocket`, **đúng** vì không có
  dependency để check. Còn lại chỉ **acceptance test live** của REL-02 (chặn Postgres tạm → health flip
  NOT_SERVING) — gộp vào phần demo/live-test.
- **topologySpread zone-hard có thể kẹt rollout** nếu 1 AZ cạn node lúc deploy — fail-safe (không downtime,
  rollout chờ) nhưng cần biết. Chọn zone-hard để đổi lấy đảm bảo tách node + AZ-resilience; chấp nhận đánh
  đổi này thay vì hostname-hard (tách node nhưng không có AZ-resilience).

## Ràng buộc đã tôn trọng
- Trong ngân sách — thay đổi $0 chi phí cố định (chỉ đổi vị trí + config, không thêm pod/node).
- Không đụng flagd. Ops vẫn riêng tư (Mandate #1). checkout Argo Rollout không đụng.

## Bằng chứng hoàn thành
1. **Demo trước mentor** (runbook [`docs/runbooks/mandate-03-drain-node-demo.md`](../runbooks/mandate-03-drain-node-demo.md)):
   tự drain 1 node app trong giờ hẹn, show Grafana SLO dashboard suốt quá trình.
2. **SLO giữ**: checkout ≥99%, browse/cart ≥99.5%, storefront p95 <1s — không rớt request khách.
3. `kubectl get pods -o wide` trước/trong/sau: mỗi service revenue luôn có ≥1 replica ready ở node khác.

## Rollback
- `git revert` PR #112/#114 → ArgoCD prune → về cấu hình cũ. Không đổi schema data, không rủi ro mất
  dữ liệu. Phát hiện qua Grafana SLO nếu có bất thường trong demo → dừng, revert.

## Trạng thái thực thi
- [x] topologySpread + rolling maxUnavailable:0 cho 9 service revenue (PR #112, merged)
- [x] Graceful shutdown preStop + grace cho 9 service revenue + template/schema (PR #114, merged)
- [x] Verify service phụ trợ degrade gọn → giữ 1 replica (không nhân đôi)
- [x] Quyết định datastore: chấp nhận residual, demo drain node app
- [ ] Chạy demo drain node + đo SLO, mời mentor confirm

---
*Ký: CDO02. Phối hợp: CDO01 (node group stateful, Performance Efficiency). Datastore HA thật (RDS/
ElastiCache) là roadmap ngoài phạm vi mandate này — xem ADR 0002 + 0005.*
