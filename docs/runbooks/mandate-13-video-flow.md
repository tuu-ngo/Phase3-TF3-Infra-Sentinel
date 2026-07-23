# Flow quay video Mandate 13

Tài liệu này mô tả **thứ tự thao tác thực tế khi quay video** cho Mandate 13. Mục tiêu là để người thực hiện không phải tự nghĩ trình tự lúc đang quay.

Tài liệu liên quan:

- Runbook chính: [mandate-13-spot-node-interruption-demo.md](mandate-13-spot-node-interruption-demo.md)
- Checklist trước demo: [mandate-13-demo-checklist.md](mandate-13-demo-checklist.md)
- Inventory production: [../evidence/mandate-13-production-inventory-20260723.md](../evidence/mandate-13-production-inventory-20260723.md)

## 1. Mục tiêu của video

Video cần chứng minh được 4 ý:

1. cluster đang dùng `spot` thật
2. workload critical path đang thực sự chạy trên `spot`
3. mất một `spot node` dưới tải không làm vỡ SLO
4. hệ thống có xu hướng co giãn node theo tải, không giữ mãi ở đỉnh

## 2. Bố cục cửa sổ cần chuẩn bị

Trước khi bấm quay, mở sẵn:

1. `AWS EC2 -> Instances`
2. `Grafana`
3. terminal thao tác chính
4. terminal theo dõi pods
5. terminal theo dõi nodes

Nếu có thêm màn hình:

6. `Cost Explorer -> Usage Quantity`

## 3. Thứ tự quay đề xuất

## 3.1. Mở đầu

Nói ngắn:

- đây là bài diễn tập Mandate 13 trên production
- mục tiêu là chứng minh spot, interruption safety và giữ SLO

Không cần nói dài. Chỉ cần đủ để người xem biết mình sắp làm gì.

## 3.2. Quay AWS EC2 -> Instances

Việc cần làm:

- bật cột `Lifecycle`
- bật cột `Instance type`
- bật cột `Architecture`

Điểm cần chỉ ra:

- node nào là `spot`
- node nào là `on-demand`
- hệ hiện tại đang là `amd64`, chưa có `arm64` live nếu đúng snapshot ngày 23/07/2026

Điểm nói nên dùng:

- production hiện đang có spot node thật
- bài demo sẽ nhắm vào spot node app-tier, không đụng vào node observability hoặc stateful nhạy cảm

## 3.3. Quay Grafana baseline

Dừng ở Grafana khoảng 10-20 giây để thấy:

- `checkout success`
- `browse/cart success`
- `storefront p95`
- `node count`

Điểm nói nên dùng:

- đây là baseline 5-10 phút trước khi can thiệp
- nếu baseline đang xấu sẵn thì kết luận đúng phải là NO-GO

## 3.4. Quay terminal để xác nhận target node

Chạy lần lượt:

```bash
kubectl get nodes -L karpenter.sh/capacity-type,node.kubernetes.io/instance-type,kubernetes.io/arch,topology.kubernetes.io/zone
kubectl -n techx-tf3 get pods -o wide
kubectl -n techx-tf3 get pdb
```

Sau đó chỉ rõ:

- node target là node nào
- node đó là `spot`
- critical services trên node đó vẫn còn replica ở node khác

Theo snapshot ngày 23/07/2026, target ưu tiên là:

```text
ip-10-0-10-199.ap-southeast-1.compute.internal
```

## 3.5. Quay giai đoạn có tải

Nếu load đang chạy sẵn, nhắc ngắn là:

- bài demo đang được thực hiện dưới tải nền có kiểm soát

Nếu chưa chạy, khởi tạo tải rồi quay lại Grafana để thấy:

- request vẫn đang có
- dashboard đang có số liệu sống

## 3.6. Quay thao tác interruption

Trong terminal thao tác chính:

```bash
kubectl cordon ip-10-0-10-199.ap-southeast-1.compute.internal
kubectl drain ip-10-0-10-199.ap-southeast-1.compute.internal --ignore-daemonsets --delete-emptydir-data
```

Điểm nói nên dùng:

- đang mô phỏng tình huống mất một spot node
- mục tiêu là buộc pod rời node target nhưng vẫn giữ đường khách hàng

## 3.7. Quay Grafana ngay trong lúc node bị drain

Đây là đoạn quan trọng nhất của video.

Phải giữ màn hình ở Grafana đủ lâu để người xem thấy:

- success rate không sập
- `p95` không vượt ngưỡng lâu
- node count và workload đang tự hồi phục

Nếu có người hỗ trợ, nên để người đó đứng ở Grafana còn người thao tác đứng ở terminal.

## 3.8. Quay terminal hậu kiểm

Chạy lại:

```bash
kubectl -n techx-tf3 get pods -o wide
kubectl get nodes -o wide
```

Điểm cần chỉ ra:

- pod đã rời node cũ
- pod đang sống ở node khác
- service critical vẫn còn replica `Ready`

## 3.9. Quay giai đoạn tải hạ xuống

Nếu bài test có load curve, sau khi giai đoạn interruption qua đi:

- giảm tải
- quay Grafana để thấy node count có xu hướng hạ xuống

Đây là bằng chứng cho phần:

- autoscale không chỉ scale up mà còn scale down

## 3.10. Quay Cost Explorer ở cuối

Video không cần chờ Cost Explorer cập nhật live. Phần này chỉ dùng để nói:

- Usage Quantity là evidence trend/history
- bằng chứng tức thì của buổi demo nằm ở `EC2 + Grafana + terminal`

Nên quay hai góc:

1. group by `Purchase Option`
2. group by `Instance Type`

## 4. Những câu không nên nói

Không nên nói:

- đã hoàn thành Graviton nếu production chưa có `arm64`
- đã pass hoàn toàn mandate nếu chưa có đủ evidence scale-down và history
- khách hàng hoàn toàn không ảnh hưởng nếu dashboard có spike rõ ràng mà chưa đo được mức ảnh hưởng thực

## 5. Những câu nên dùng

Nên nói:

- đây là target spot node đã được pre-flight trước
- critical path vẫn còn replica ở node khác
- dashboard đang cho thấy success rate vẫn trong ngưỡng
- đây là bằng chứng runtime thực tế, không phải chỉ là cấu hình trên Git

## 6. Kết video nên chốt thế nào

Chốt bằng 4 ý ngắn:

1. production đang có spot node thật
2. critical path đã thực sự chạy trên spot
3. mất một spot node không làm vỡ SLO trong cửa sổ diễn tập
4. hệ thống vẫn cần evidence tiếp cho các phần chưa claim, đặc biệt là nếu chưa có `arm64` live

## 7. Abort ngay nếu gặp các tín hiệu này trong lúc quay

- success rate rơi mạnh và không hồi nhanh
- `storefront p95` phá ngưỡng kéo dài
- pod critical chuyển sang `Pending` mà không reschedule được
- quan sát viên trên Grafana báo dashboard chuyển đỏ
- target node thực tế khác inventory ban đầu

Nếu có một trong các tín hiệu trên:

- dừng bài diễn tập
- nói rõ đây là `NO-GO`
- lưu lại bằng chứng để biến thành action item thay vì cố quay cho xong
