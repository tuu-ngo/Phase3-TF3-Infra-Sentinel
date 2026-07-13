# ADR 0003 — Mandate #1 (cổng vận hành riêng tư): phần CDO02 (Reliability + Ops + Auditability)

**Ngày:** 12/07/2026
**Người quyết định (ký):** CDO02 (Reliability + Cost Optimization)
**Directive:** [`mandates/MANDATE-01-network-exposure.md`](../../mandates/MANDATE-01-network-exposure.md) — hạn **14/07/2026**
**Trạng thái:** 🟡 Đã thiết kế + chuẩn bị — **chờ AWS mở account để deploy + verify** (xem postmortem 0002)
**Phạm vi ADR này:** **chỉ phần CDO02**. Quyết định least-exposure/route nào đóng là **Security → CDO01**.
CDO02 chịu trách nhiệm: cắt chuyển **zero-downtime** (Reliability), **change management + rollback + runbook**
(Operational Excellence), và **ghi vết truy cập** cổng ops (Auditability).

---

## Bối cảnh

Mandate #1 yêu cầu: storefront giữ public, **mọi cổng vận hành (Grafana, Jaeger, ArgoCD, các UI
observability/CD) phải riêng tư** — internet công khai không vào được, người có quyền vẫn vào được,
và mentor phải có đường vào để chấm.

**Hiện trạng phơi bày (đã xác nhận từ config Envoy `frontend-proxy`):** ALB internet-facing →
`frontend-proxy` (Envoy) đang route **công khai** cả `/grafana`, `/jaeger/ui`, `/loadgen`, `/feature`
(flagd-ui) — nghĩa là Grafana (đang **anonymous-admin**), Jaeger, load-generator UI, flagd-ui **đều
phơi ra internet** qua cùng cổng với storefront. ArgoCD hiện là ClusterIP (chỉ vào qua port-forward)
— đã riêng tư sẵn.

## Quyết định (phần CDO02)

CDO02 **không** tự sửa route Envoy (đó là hành động least-exposure của CDO01). CDO02 cam kết 3 việc
để mandate được thực thi an toàn và chấm được:

1. **Reliability — cắt chuyển zero-downtime.** Khi CDO01 gỡ các route ops khỏi Envoy, thay đổi được
   áp qua rolling update. `frontend-proxy` đã có **2 replica + PDB (REL-01)** nên rollout không làm
   đứt storefront/checkout. CDO02 verify SLO checkout (≥99%) không tụt trước/trong/sau cắt chuyển.
2. **Operational Excellence — change management + rollback + runbook.**
   - Thay đổi đi qua **GitOps/ArgoCD** (không sửa tay cluster), 1 commit → sync.
   - **Rollback** = `git revert` commit Envoy + ArgoCD re-sync (≤ vài phút).
   - **Runbook truy cập riêng tư** cho team + mentor: [`docs/runbooks/private-access-to-ops-uis.md`](../runbooks/private-access-to-ops-uis.md).
3. **Auditability — ghi vết ai truy cập cổng ops, khi nào.** Mọi đường vào riêng tư đi qua **SSM
   bastion**. Bật **SSM Session Manager logging → CloudWatch Logs** (`infra/ssm-session-logging.tf`)
   → mỗi phiên vào bastion ghi lại IAM identity + thời điểm + lệnh chạy. Bổ sung ArgoCD audit log
   (server logs) cho đường CD.

## Đánh đổi đã cân

- **Truy cập ops chậm hơn 1 chút** (phải qua bastion tunnel + port-forward thay vì mở URL) — chấp
  nhận, đổi lấy bề mặt tấn công gần như bằng 0 cho cổng ops. Đây đúng tinh thần mandate.
- **Không đổi cách khách vào storefront** — giữ nguyên public path, không rủi ro cho luồng ra tiền.
- **SSM session logging tốn thêm không đáng kể** (CloudWatch Logs vài MB/tuần) — nằm gọn trong ngân
  sách $300/tuần. Đổi lấy Auditability đo được.
- **Cân nhắc rồi loại:** đặt Grafana/Jaeger sau 1 ALB nội bộ riêng + VPN — mạnh hơn nhưng tốn thêm
  ALB + dựng VPN, không cần thiết khi bastion SSM đã đủ (người có quyền vẫn vào, công khai thì không).

## Ràng buộc đã tôn trọng
- **Zero-downtime storefront** — rolling update, 2 replica + PDB.
- **flagd KHÔNG đụng:** chỉ gỡ `/feature` (flagd-**ui**). **Giữ nguyên `/flagservice`** (đường service
  đọc flag — gỡ là disqualify). ⚠️ Điểm bắt buộc kiểm khi review diff Envoy của CDO01.
- **Trong ngân sách** — không thêm hạ tầng tốn kém.

## Bằng chứng hoàn thành (evidence — để mentor tự verify)
1. `curl https://<storefront-public-url>/` → **200** (storefront vẫn public).
2. `curl https://<storefront-public-url>/grafana` → **404/403** (ops không còn public).
3. Mentor theo runbook: mở SSM tunnel + `kubectl port-forward svc/grafana` → **vào được** Grafana/
   Jaeger/ArgoCD qua đường riêng.
4. CloudWatch Logs group SSM sessions → thấy bản ghi phiên truy cập (ai/khi nào) — bằng chứng Auditability.
5. SLO checkout trên Grafana trong cửa sổ cắt chuyển không tụt dưới 99%.

## Rollback plan
- Envoy route: `git revert <commit>` → ArgoCD re-sync → ops route công khai trở lại (nếu cắt chuyển
  gây sự cố ngoài dự kiến). Thời gian phát hiện: ngay, qua smoke test storefront + ops sau sync.
- SSM logging: `terraform apply` bỏ block logging (hoặc revert PR) — không ảnh hưởng đường vào, chỉ
  tắt ghi vết.

## Trạng thái thực thi
- [ ] (CDO01) gỡ route ops khỏi Envoy, giữ `/flagservice` — CDO02 review diff xác nhận flagd an toàn
- [ ] Deploy SSM session logging (`infra/ssm-session-logging.tf`) — chờ account mở
- [ ] Verify evidence 1-5 ở trên (chờ account mở + storefront về)
- [ ] Mời mentor verify theo runbook

---
*Ký: CDO02. Phối hợp: CDO01 (Security — least-exposure Envoy). Deadline 14/07 đang chịu rủi ro do
account hold ngoài tầm kiểm soát (đã escalate mentor) — mọi thứ đã sẵn để deploy tức thì khi account về.*
