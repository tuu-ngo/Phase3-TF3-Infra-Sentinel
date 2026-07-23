# Inventory production cho Mandate 13 - snapshot ngày 23/07/2026

Tài liệu này tách riêng khỏi runbook để ghi lại **phân loại thực tế trên production** tại thời điểm chuẩn bị diễn tập Mandate 13. Mục tiêu là:

- biết rõ node nào là `spot`
- biết rõ node nào là `on-demand`
- biết node nào có thể chọn làm target diễn tập
- biết node nào không nên đụng vào vì đang giữ observability hoặc workload nền quan trọng

## 1. Snapshot node hiện tại

Nguồn kiểm tra:

```bash
kubectl get nodes -L karpenter.sh/capacity-type,topology.kubernetes.io/zone,node.kubernetes.io/instance-type,kubernetes.io/arch
```

Snapshot ghi nhận ngày **23/07/2026**:

| Node | Lifecycle | Zone | Instance type | Architecture | Nhận định sử dụng |
|---|---|---|---|---|---|
| `ip-10-0-10-199` | `spot` | `ap-southeast-1a` | `t3.medium` | `amd64` | Spot app node ổn định, có thể là target ưu tiên |
| `ip-10-0-21-42` | `spot` | `ap-southeast-1b` | `t3.medium` | `amd64` | Spot node mới lên, chưa nên chọn làm target đầu tiên |
| `ip-10-0-33-255` | `spot` | `ap-southeast-1c` | `t3.medium` | `amd64` | Spot app node, không ưu tiên vì `otel-gateway` có restart gần đây |
| `ip-10-0-40-78` | `spot` | `ap-southeast-1c` | `t3.medium` | `amd64` | Spot node mới, hiện chỉ đang nhận replica mới |
| `ip-10-0-24-177` | `on-demand` | `ap-southeast-1b` | `t3.large` | `amd64` | Node nền tương đối an toàn, giữ workload ứng dụng phụ và observability |
| `ip-10-0-26-153` | `on-demand` | `ap-southeast-1b` | `t3.large` | `amd64` | Node nền cho workload phụ trợ |
| `ip-10-0-4-166` | `on-demand` | `ap-southeast-1a` | `t3.medium` | `amd64` | Không nên đụng nếu đang là node dành cho stateful/datastore |
| `ip-10-0-43-83` | `on-demand` | `ap-southeast-1c` | `t3.large` | `amd64` | Node nền cho workload phụ trợ |
| `ip-10-0-8-134` | `on-demand` | `ap-southeast-1a` | `t3.large` | `amd64` | Không chọn làm target vì đang giữ observability plane |

## 2. Phân loại node theo mục tiêu diễn tập

### 2.1. Node có thể chọn làm target spot interruption

| Node | Lý do |
|---|---|
| `ip-10-0-10-199` | Đang chạy app-tier critical path chuẩn, có replica tương ứng ở node khác, và `otel-gateway` trên node này đang ổn định |

### 2.2. Node spot nên tránh chọn làm target đầu tiên

| Node | Lý do |
|---|---|
| `ip-10-0-33-255` | Có `otel-gateway` restart `8` lần gần đây, dễ làm nhiễu kết quả demo |
| `ip-10-0-21-42` | Node mới lên, chưa phải baseline ổn định |
| `ip-10-0-40-78` | Node mới lên, hiện mới nhận pod `product-reviews`, chưa phải target đẹp để diễn tập đầu tiên |

### 2.3. Node on-demand không dùng làm target

| Node | Lý do |
|---|---|
| `ip-10-0-8-134` | Đang giữ `grafana`, `prometheus`, `opensearch`, `load-generator` |
| `ip-10-0-24-177` | Đang giữ `jaeger`, `flagd`, `fraud-detection`, `llm`, `accounting` |
| `ip-10-0-26-153` | Đang giữ `aiops-engine`, `image-provider` |
| `ip-10-0-43-83` | Đang giữ `ad`, `email`, `recommendation`, `cloudflared` |
| `ip-10-0-4-166` | Xem như node nhạy cảm, không dùng cho bài diễn tập app-tier |

## 3. Mapping pod placement hiện tại

Nguồn kiểm tra:

```bash
kubectl -n techx-tf3 get pods -o wide
```

### 3.1. Critical path đang nằm trên spot

| Service | Replica spot hiện tại |
|---|---|
| `cart` | `ip-10-0-10-199`, `ip-10-0-33-255` |
| `checkout` | `ip-10-0-10-199`, `ip-10-0-33-255` |
| `currency` | `ip-10-0-10-199`, `ip-10-0-33-255` |
| `frontend` | `ip-10-0-10-199`, `ip-10-0-33-255` |
| `frontend-proxy` | `ip-10-0-10-199`, `ip-10-0-33-255` |
| `payment` | `ip-10-0-10-199`, `ip-10-0-33-255` |
| `product-catalog` | `ip-10-0-10-199`, `ip-10-0-33-255` |
| `quote` | `ip-10-0-10-199`, `ip-10-0-33-255` |
| `shipping` | `ip-10-0-10-199`, `ip-10-0-33-255` |

Nhận định:

- Đây là dấu hiệu tốt cho Mandate 13 vì critical path đã thực sự chạy trên spot.
- Khi diễn tập với `ip-10-0-10-199`, mỗi service trên đường doanh thu vẫn còn replica ở `ip-10-0-33-255`.

### 3.2. Replica mới đã bắt đầu lan sang các spot node mới

| Service | Replica spot hiện tại |
|---|---|
| `product-reviews` | `ip-10-0-21-42`, `ip-10-0-40-78` |

Nhận định:

- Cluster đã bắt đầu phân phối thêm workload sang spot node mới.
- Điều này tốt cho câu chuyện scale-out, nhưng cũng có nghĩa inventory phải được kiểm tra lại sát giờ quay video, không dùng snapshot cũ.

### 3.3. Observability và workload nền đang ở on-demand

| Node | Workload nổi bật |
|---|---|
| `ip-10-0-8-134` | `grafana`, `prometheus`, `opensearch`, `load-generator` |
| `ip-10-0-24-177` | `jaeger`, `flagd`, `llm`, `accounting`, `fraud-detection` |
| `ip-10-0-26-153` | `aiops-engine`, `image-provider` |
| `ip-10-0-43-83` | `ad`, `email`, `recommendation`, `cloudflared` |

Nhận định:

- Cách đặt này phù hợp với mục tiêu diễn tập Mandate 13: app-tier chạy trên spot, còn observability plane và workload nền vẫn giữ trên on-demand.
- Vì vậy video nên giải thích rõ đây là chủ đích bảo vệ mặt quan sát và mặt điều hành khi diễn tập.

## 4. Kết luận dùng cho buổi quay video

### 4.1. Có thể claim ngay

- Cluster đang có **spot node thật** trên production.
- Critical path `browse -> cart -> checkout` đang thực sự chạy trên spot.
- Observability plane chính vẫn nằm ở on-demand.

### 4.2. Không nên claim quá tay

- Chưa có `arm64` live; toàn bộ node hiện vẫn là `amd64`.
- Vì vậy chưa nên nói Mandate 13 đã hoàn thành phần `Graviton`.

### 4.3. Target diễn tập đề xuất

- **Ưu tiên:** `ip-10-0-10-199`
- **Không ưu tiên:** `ip-10-0-33-255`
- **Chưa nên chọn đầu tiên:** `ip-10-0-21-42`, `ip-10-0-40-78`

## 5. Cách dùng tài liệu này

Trước khi quay video hoặc bấm live demo:

1. đối chiếu lại `kubectl get nodes`
2. nếu inventory khác snapshot này thì cập nhật lại nhanh
3. chỉ dùng tài liệu này như **baseline phân loại**
4. quyết định GO/NO-GO cuối cùng vẫn phải bám thêm vào:
   - baseline SLO 5-10 phút trước demo
   - PDB hiện tại
   - pod placement hiện tại
   - event bất thường đang mở hay không
