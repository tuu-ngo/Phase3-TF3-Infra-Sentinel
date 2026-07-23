# Checklist thực thi Mandate 13 trên production

Checklist này dùng ngay trước buổi diễn tập để trả lời một câu hỏi duy nhất:

**Có đủ điều kiện để bấm live demo hay chưa?**

Tài liệu này không thay thế runbook chính. Nó là bản ngắn gọn để người thực hiện không phải lật lại toàn bộ runbook dài trong lúc chuẩn bị quay video hoặc đứng trước mentor.

Tài liệu liên quan:

- Runbook chính: [mandate-13-spot-node-interruption-demo.md](mandate-13-spot-node-interruption-demo.md)
- Inventory production: [../evidence/mandate-13-production-inventory-20260723.md](../evidence/mandate-13-production-inventory-20260723.md)

## 1. Checklist GO / NO-GO trước giờ bấm

Đánh dấu từng mục. Nếu có bất kỳ mục nào là `Không`, kết luận phải là **NO-GO**.

| Câu hỏi | Có / Không | Ghi chú |
|---|---|---|
| Đã mở được `kubectl`, Grafana, AWS EC2 console chưa? |  |  |
| Baseline SLO 5-10 phút gần nhất đang ổn chưa? |  |  |
| `checkout success >= 99%` chưa? |  |  |
| `browse/cart success >= 99.5%` chưa? |  |  |
| `storefront p95 < 1s` chưa? |  |  |
| Không có incident đang mở sẵn chưa? |  |  |
| Không có rollout dở dang hoặc autoscale bất thường chưa? |  |  |
| Đã xác nhận node target là `spot` thật chưa? |  |  |
| Đã xác nhận node target không giữ stateful workload nhạy cảm chưa? |  |  |
| Mỗi service critical trên node target đều còn replica `Ready` ở node khác chưa? |  |  |
| PDB của nhóm service critical có `ALLOWED DISRUPTIONS >= 1` chưa? |  |  |
| Có người canh Grafana trong lúc thao tác terminal chưa? |  |  |
| Đã mở sẵn màn hình quay video chưa? |  |  |

## 2. Node target mặc định theo snapshot ngày 23/07/2026

Theo inventory live hiện tại:

- **Ưu tiên chọn:** `ip-10-0-10-199`
- **Không ưu tiên chọn:** `ip-10-0-33-255`
- **Chưa chọn đầu tiên:** `ip-10-0-21-42`, `ip-10-0-40-78`

Lý do:

- `ip-10-0-10-199` đang là spot node ổn định và có critical-path replica song song ở node khác
- `ip-10-0-33-255` có `otel-gateway` restart gần đây
- `ip-10-0-21-42` và `ip-10-0-40-78` là spot node mới lên, không phải baseline đẹp cho buổi diễn tập đầu tiên

## 3. Lệnh kiểm tra nhanh trước demo

### 3.1. Kiểm tra node inventory

```bash
kubectl get nodes -L karpenter.sh/capacity-type,node.kubernetes.io/instance-type,kubernetes.io/arch,topology.kubernetes.io/zone
```

### 3.2. Kiểm tra pod placement

```bash
kubectl -n techx-tf3 get pods -o wide
```

### 3.3. Kiểm tra PDB

```bash
kubectl -n techx-tf3 get pdb
```

### 3.4. Kiểm tra pod trên node target

```bash
NODE=ip-10-0-10-199.ap-southeast-1.compute.internal
kubectl -n techx-tf3 get pods -o wide --field-selector spec.nodeName=$NODE
```

## 4. Màn hình phải mở sẵn trước khi quay

Tối thiểu mở sẵn:

1. `AWS EC2 -> Instances`
2. `Grafana`
3. terminal theo dõi pods
4. terminal theo dõi nodes

Nếu có thể, mở thêm:

5. `Cost Explorer -> Usage Quantity`
6. terminal theo dõi `nodepool,nodeclaim`

## 5. Điều kiện dừng ngay

Nếu xuất hiện một trong các tín hiệu sau, phải dừng bài diễn tập:

- success rate tụt rõ rệt và không hồi nhanh
- `storefront p95` vượt ngưỡng và giữ cao
- pod critical không reschedule được
- pod critical chuyển sang `Pending` kéo dài
- PDB không cho eviction tiếp
- observability plane có dấu hiệu mất quan sát
- node target thực tế không còn là node phù hợp như inventory trước đó

## 6. Kết quả mong đợi để coi là PASS buổi demo

Buổi demo được coi là đạt nếu cùng lúc chứng minh được:

- node target là `spot`
- node bị cô lập/drain nhưng đường `browse -> cart -> checkout` không gãy
- success rate vẫn giữ trong ngưỡng mandate
- `p95` không phá ngưỡng `1s`
- pod được reschedule sang node khác
- sau khi tải hạ, node count có xu hướng co xuống lại

## 7. Bằng chứng tối thiểu phải lưu sau demo

Tối thiểu lưu lại:

1. video toàn bộ buổi demo
2. ảnh EC2 Instances có cột `Lifecycle`, `Instance type`, `Architecture`
3. ảnh Grafana baseline trước demo
4. ảnh Grafana trong lúc interruption
5. ảnh Grafana sau khi recovery
6. ảnh terminal thể hiện `cordon/drain` đúng node
7. ảnh terminal thể hiện pod reschedule
8. ảnh hoặc note từ Cost Explorer cho phần trend/history

## 8. Kết luận nhanh cuối checklist

Chỉ dùng một trong hai câu sau:

- `GO: baseline ổn, target phù hợp, replica và PDB đạt, đủ điều kiện diễn tập`
- `NO-GO: còn gap ở baseline hoặc placement hoặc disruption safety, chưa được bấm live`
