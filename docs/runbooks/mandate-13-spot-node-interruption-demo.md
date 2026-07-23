# Runbook - Mandate 13: diễn tập spot node interruption an toàn trên production

Runbook này dùng để chuẩn bị và thực hiện phần khó nhất của Mandate 13:

- chứng minh workload chạy được trên spot
- chứng minh khi mất 1 spot node giữa lúc có tải thì luồng browse -> cart -> checkout không rớt request
- giữ SLO trong suốt cửa sổ diễn tập

Runbook này cố ý ưu tiên an toàn production hơn là "demo cho bằng được". Nếu pre-flight không đạt thì kết luận đúng phải là **NO-GO**, không được cố ép diễn tập.

## 1. Mục tiêu

Mục tiêu của bài diễn tập:

1. chọn đúng một node spot đang phục vụ workload stateless phù hợp
2. tạo tải kiểm soát được trên storefront
3. cô lập node đó bằng `cordon`
4. thay thế node "on-the-fly" bằng cách drain hoặc terminate theo đường an toàn
5. chứng minh trong toàn bộ cửa sổ đó SLO không tụt dưới ngưỡng mandate

Ngưỡng Mandate 13 cần giữ:

- checkout success >= 99%
- browse/cart success >= 99.5%
- storefront p95 < 1s

## 2. Không dùng runbook này khi nào

Không dùng runbook này nếu rơi vào một trong các điều kiện sau:

- chưa xác nhận node mục tiêu thực sự là spot
- node mục tiêu đang chứa workload stateful hoặc thành phần hạ tầng nhạy cảm
- service revenue trên node mục tiêu không có replica `Ready` ở node khác
- PDB của service trọng yếu đang `ALLOWED DISRUPTIONS = 0`
- Grafana/Prometheus/Jaeger đang lỗi hoặc không xem được
- cluster đang có incident mở, rollout dở dang, hoặc error budget đang cháy
- load test nền chưa ổn định

Nếu một trong các điều kiện trên xảy ra, kết luận phải là:

`NO-GO: chưa đủ an toàn để diễn tập spot interruption trên production`

## 3. Điều kiện tiên quyết

Trước khi chạy, phải có đủ các điều kiện sau:

- truy cập được `kubectl`
- mở được Grafana
- mở được Jaeger nếu cần trace sâu
- xác nhận Karpenter/spot node pool đang healthy
- có ít nhất 1 node spot đang chứa workload stateless
- đã có baseline hiện tại của node on-demand và node spot

## 4. Chuẩn bị màn hình evidence

Mở sẵn ba nguồn evidence trước khi thao tác:

1. Grafana dashboard có:
   - checkout success rate
   - browse/cart success rate
   - storefront p95
   - số node theo thời gian nếu có
2. terminal theo dõi pod:

```bash
kubectl -n techx-tf3 get pods -o wide -w
```

3. terminal theo dõi node:

```bash
kubectl get nodes -o wide -w
```

Nếu có thể, mở thêm:

```bash
kubectl get nodepool,nodeclaim -w
```

## 4.1. Bảng inventory bắt buộc trước khi diễn tập

Trước khi bấm diễn tập, nên chụp hoặc điền nhanh một bảng inventory tối thiểu để tránh nhầm node:

| Node | Lifecycle | Instance type | Zone | Architecture | Vai trò dự kiến |
|---|---|---|---|---|---|
| `<node-1>` | `spot` / `on-demand` | `t3.medium`... | `ap-southeast-1a/b/c` | `amd64` / `arm64` | target / baseline / stateful |

Tối thiểu phải phân loại được:

- node nào là `spot`
- node nào là `on-demand`
- node nào đang là node stateful hoặc không được phép đụng vào

Ví dụ lệnh thu thập:

```bash
kubectl get nodes \
  -L karpenter.sh/capacity-type,node.kubernetes.io/instance-type,kubernetes.io/arch,topology.kubernetes.io/zone
```

Với hệ thống hiện tại, bảng này còn giúp chứng minh một gap thật của Mandate 13:

- cluster đã có node `spot`
- nhưng spot node pool hiện vẫn khóa `amd64`
- nên phần `Graviton` chưa đạt và phải được ghi nhận trung thực

## 5. Pre-flight check bắt buộc

### 5.1. Xác định node spot hiện tại

```bash
kubectl get nodes -L karpenter.sh/capacity-type,node.kubernetes.io/instance-type,topology.kubernetes.io/zone
```

Điều cần thấy:

- có node với `karpenter.sh/capacity-type=spot`
- ghi lại node name, instance type, zone

### 5.2. Xác định pod nào đang nằm trên node spot đó

```bash
NODE=<ten-node-spot>
kubectl -n techx-tf3 get pods -o wide --field-selector spec.nodeName=$NODE
```

Điều cần thấy:

- chỉ có workload stateless hoặc workload được chấp nhận diễn tập
- không có pod stateful quan trọng

Nên chụp thêm một bảng ngắn:

| Node target | Lifecycle | Critical pods on node | Có replica Ready ở node khác? | GO / NO-GO |
|---|---|---|---|---|
| `<node-spot>` | `spot` | `checkout`, `cart`... | `Có/Không` | `GO/NO-GO` |

### 5.3. Kiểm tra replica an toàn ở node khác

Với từng service revenue trên node spot mục tiêu, kiểm tra:

```bash
kubectl -n techx-tf3 get pods -o wide \
  -l 'opentelemetry.io/name in (frontend,frontend-proxy,product-catalog,cart,checkout,payment,currency,shipping,quote,product-reviews)'
```

Điều kiện để GO:

- mỗi service trọng yếu nằm trên node spot mục tiêu phải còn ít nhất 1 pod `Ready` ở node khác
- không được có service critical chỉ còn đúng 1 pod sống trên node sắp diễn tập

### 5.4. Kiểm tra PDB

```bash
kubectl -n techx-tf3 get pdb
```

Điều kiện để GO:

- các service trọng yếu liên quan phải có `ALLOWED DISRUPTIONS >= 1`

### 5.5. Kiểm tra workload stateful không dính vào node spot mục tiêu

Kiểm tra riêng các thành phần có rủi ro cao:

```bash
kubectl -n techx-tf3 get pods -o wide | grep -E 'postgres|valkey|kafka|opensearch|prometheus|grafana|jaeger'
```

Điều kiện để GO:

- không diễn tập trên node chứa datastore single-replica hoặc observability plane nhạy cảm

### 5.6. Kiểm tra baseline SLO trước diễn tập

Trong cửa sổ 5-10 phút trước khi làm, dashboard phải ổn định:

- checkout success đang >= 99%
- browse/cart success đang >= 99.5%
- storefront p95 đang < 1s
- không có spike lỗi đang mở sẵn

## 6. Quyết định GO / NO-GO

Chỉ được GO khi đồng thời thỏa:

- node mục tiêu là node spot thật
- node đó không chứa stateful workload rủi ro cao
- service critical trên node đó đều có replica `Ready` ở node khác
- PDB không chặn cứng
- dashboard và quan sát đang khỏe

Nếu thiếu bất kỳ điều kiện nào ở trên:

- không chạy diễn tập
- ghi nhận gap
- biến nó thành action item cho Mandate 13

## 7. Tạo tải kiểm soát

Không diễn tập giữa traffic người dùng thật nếu chưa có cửa sổ an toàn.

Ưu tiên dùng tải kiểm soát qua `load-generator` hoặc Locust ở mức nhẹ đến vừa, đủ để có request thật nhưng không tạo một bài stress test mới.

Mức khuyến nghị:

- dùng tải nền ổn định
- không mở thử nghiệm bằng 200 user ngay từ đầu nếu mục tiêu chỉ là chứng minh interruption

Ví dụ:

```bash
kubectl -n techx-tf3 port-forward svc/load-generator 8089:8089
```

Sau đó đặt bài chạy ở mức vừa phải trong Locust UI.

## 8. Cách diễn tập ưu tiên an toàn

Ưu tiên diễn tập theo hai pha.

### Pha A - cordon trước

```bash
NODE=<ten-node-spot>
kubectl cordon "$NODE"
```

Mục đích:

- chặn pod mới schedule vào node này
- ổn định mặt bằng trước khi đẩy disruption tiếp theo

Theo dõi 1-2 phút:

- dashboard không xấu đi
- không có pod mới bị kẹt `Pending`

### Pha B - gây mất node theo đường được kiểm soát

Ưu tiên đường an toàn nhất là `drain` node spot mục tiêu:

```bash
kubectl drain "$NODE" \
  --ignore-daemonsets \
  --delete-emptydir-data \
  --grace-period=30 \
  --timeout=180s
```

Vì sao ưu tiên `drain`:

- gần với hành vi node bị thu hồi nhưng vẫn tôn trọng PDB và graceful shutdown
- cho phép quan sát rõ reschedule
- ít bạo lực hơn terminate thẳng EC2

Chỉ dùng terminate instance nếu:

- đã qua được bài `drain`
- mentor yêu cầu đúng tình huống reclaim mạnh hơn
- team chấp nhận mức rủi ro cao hơn

## 9. Điều phải theo dõi trong lúc diễn tập

Theo dõi liên tục:

1. Grafana:
   - checkout success
   - browse/cart success
   - storefront p95
2. pod reschedule:

```bash
kubectl -n techx-tf3 get pods -o wide -w
```

3. node/nodeclaim:

```bash
kubectl get nodes -w
kubectl get nodeclaim -w
```

Điều mong đợi:

- pod critical được giữ `Ready` nhờ replica còn lại
- Karpenter có thể bù lại node spot nếu scheduler cần capacity
- không có lỗi dây chuyền sang checkout path

## 10. Điều kiện abort ngay

Dừng diễn tập ngay nếu có một trong các dấu hiệu sau:

- checkout success tụt dưới 99%
- browse/cart success tụt dưới 99.5%
- storefront p95 vượt 1s và không hồi nhanh
- pod critical rơi vào `Pending` kéo dài
- datastore hoặc observability plane bị ảnh hưởng
- lỗi người dùng thật bắt đầu tăng rõ trên dashboard

Nếu chạm abort:

1. dừng tải kiểm soát
2. `uncordon` node nếu còn tồn tại
3. theo dõi pod/node hồi phục
4. ghi nhận đây là `NO-GO` cho live spot interruption hiện tại

## 11. Hậu kiểm

Sau khi kết thúc:

```bash
kubectl uncordon "$NODE"
```

Chụp lại:

- node inventory sau diễn tập
- pod placement sau diễn tập
- dashboard SLO trong toàn bộ cửa sổ

Phải trả lời được 4 câu hỏi:

1. node spot mục tiêu là node nào
2. service nào bị ảnh hưởng trên node đó
3. trong cửa sổ disruption SLO có giữ hay không
4. cluster có co/bù node đúng như kỳ vọng hay không

Ngoài ra nên chốt lại bảng evidence tối thiểu sau buổi diễn tập:

| Hạng mục | Evidence cần lưu |
|---|---|
| Inventory node | danh sách node `spot` / `on-demand`, instance type, zone, architecture |
| Node mục tiêu | node spot nào đã được chọn và vì sao |
| Safety check | pod critical trên node mục tiêu có replica ở node khác |
| Disruption window | thời điểm cordon, drain, reschedule |
| SLO window | checkout success, browse/cart success, storefront p95 |
| Kết luận | PASS / NO-GO / cần khắc phục gì trước lần sau |

## 12. Tiêu chí PASS cho Mandate 13 phần interruption

Chỉ nên kết luận PASS nếu:

- disruption xảy ra trên node spot thật
- có tải thực trong lúc diễn tập
- luồng browse -> cart -> checkout không rớt request vượt ngưỡng mandate
- evidence dashboard và node/pod timeline khớp nhau

## 13. Ghi chú riêng cho hệ thống hiện tại

Từ trạng thái hiện tại đã quan sát:

- cluster có node spot thật
- nhưng node pool spot hiện đang khóa `kubernetes.io/arch=amd64`, nên chưa có phần Graviton của Mandate 13
- vì vậy bài spot interruption có thể chuẩn bị trước, nhưng tổng thể Mandate 13 vẫn còn việc riêng về Graviton, spot ratio và evidence node-hours

Nói cách khác:

- runbook này giúp xử phần khó nhất về Reliability của Mandate 13
- nhưng không tự thân làm Mandate 13 hoàn tất
