# Runbook — Load test flash sale (Mandate #2): 200 user / 15 phút, đo SLO + cost

**Mục tiêu:** chứng minh hệ thống gánh **200 user đồng thời trong 15 phút** mà **giữ SLO**
(checkout ≥99%, browse/cart ≥99.5%, p95 <1s) và **cost/request không phình**, rồi **co xuống** sau đỉnh.

**Điều kiện tiên quyết:** đã deploy metrics-server EKS add-on + HPA + Karpenter Spot (Mandate #2), account
AWS đã mở, cluster truy cập được (qua bastion — xem recovery runbook).

---

## Bước 0 — Chụp baseline TRƯỚC test
```bash
kubectl -n techx-tf3 get hpa                       # replicas hiện tại (min)
kubectl get nodes                                   # số node (kỳ vọng 3)
kubectl -n techx-tf3 top pods                       # CPU/mem baseline
```
- Ghi **cost baseline** (AWS Cost Explorer, chi phí/ngày trước test).

## Bước 1 — Chạy load-generator ở 200 user / 15 phút
`load-generator` là Locust. Điều khiển qua env hoặc UI (truy cập UI qua đường **riêng tư**, không public):
```bash
# Cách A - set cấu hình rồi restart loadgen:
kubectl -n techx-tf3 set env deploy/load-generator LOCUST_USERS=200 LOCUST_SPAWN_RATE=20
kubectl -n techx-tf3 rollout restart deploy/load-generator
# đợi ~15 phút

# Cách B - qua Locust UI (private): port-forward rồi điều khiển
kubectl -n techx-tf3 port-forward svc/load-generator 8089:8089
#   -> http://localhost:8089  đặt Users=200, Spawn rate=20, Run 15m
```
> Cùng cấu hình tải (200 user, 15 phút) cho cả 4 TF để so công bằng — theo mandate.

## Bước 2 — Quan sát trong lúc test (SLO + co giãn)
Grafana (private, qua bastion + port-forward — xem `private-access-to-ops-uis.md`):
- `apm-dashboard`: checkout success ≥99%, browse/cart ≥99.5%, p95 <1s.
- `postgresql-dashboard`: connection count không cạn (REL-05 giữ pool).
```bash
watch kubectl -n techx-tf3 get hpa      # thấy replicas CO LÊN theo tải
watch kubectl get nodes                  # Karpenter thêm Spot node nếu pod Pending
kubectl get nodepool,nodeclaim           # NodePool/NodeClaim trạng thái Spot burst
```

## Bước 3 — Sau đỉnh: xác nhận CO XUỐNG (không neo tài nguyên/tiền)
Tắt tải (Locust stop / LOCUST_USERS về mức thường), rồi đợi ~5-10 phút:
```bash
kubectl -n techx-tf3 get hpa      # replicas co về min (2)
kubectl get nodes                  # node co về baseline on-demand
kubectl get nodeclaim              # Spot NodeClaim được consolidate/xóa khi rảnh
```
- Đây là bằng chứng **co lên → co xuống**: pod & node trở về baseline.

## Bước 4 — Nộp evidence (theo README mandate)
1. **SLO giữ:** screenshot/dexport Grafana 15 phút @200 user — 3 ngưỡng SLO đều đạt.
2. **Cost trong trần:** cost trước/sau (Cost Explorer); tính **cost/đơn** = cost cửa sổ test / số đơn
   thành công → so baseline, chứng minh **không phình**.
3. **Co giãn:** bảng replicas + node theo mốc (trước / đỉnh / sau) cho thấy về lại mức thường.
4. Cho mentor lệnh chạy lại (Bước 1) để tự chứng kiến.

## Nếu SLO tụt trong test (rollback)
- Dừng tải ngay (Locust stop).
- Nếu do HPA/Karpenter bất ổn → `git revert` manifest Mandate #2 → ArgoCD prune → về baseline replicas cố định.
- Điều tra bottleneck (thường: CPU request quá thấp làm HPA scale sai, hoặc datastore bão hòa) → tinh
  chỉnh target/request → test lại. Bottleneck tầng latency/perf: phối hợp CDO01.

## Ràng buộc suốt test
- Storefront public, ops private (Mandate #1) — không mở public cổng ops để tiện xem.
- **KHÔNG đụng flagd.** Không tăng cứng tài nguyên cố định để "chắc gánh nổi" (mandate cấm).
