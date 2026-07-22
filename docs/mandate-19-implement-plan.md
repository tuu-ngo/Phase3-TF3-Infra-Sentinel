# Kế hoạch triển khai [MANDATE 19]: Xuống mềm khi vượt trần (Graceful Degradation)

Mục tiêu của kế hoạch này là cấu hình Envoy proxy để thực hiện Load Shedding (cắt bớt tải) đối với các request không thiết yếu (như browse/search) khi hệ thống chịu tải cao, đồng thời ưu tiên bảo vệ các request thiết yếu là `/api/checkout`.

## 1. Cấu hình Envoy Proxy (`envoy.tmpl.yaml`)

**Kích hoạt filter Local Rate Limit**
- Thêm `envoy.filters.http.local_ratelimit` vào danh sách `http_filters` của HTTP Connection Manager, đặt trước filter `router`. Filter này sẽ đóng vai trò engine xử lý rate limit ngay tại Envoy (không cần external Redis).

**Cấu hình phân luồng (Routing & Per-Route Rate Limiting)**
Hiện tại tất cả traffic vào `frontend` đều qua route `/`. Chúng ta sẽ tách riêng:
1.  **Route ưu tiên (`/api/checkout`)**: Thêm rule match prefix `/api/checkout`, trỏ vào cluster `frontend`. Route này sẽ **không** bị áp dụng rate limit của route `/` (hoặc sẽ được cấp một quota cực lớn) để đảm bảo không bao giờ bị shed load do Envoy.
2.  **Route hy sinh (`/`)**: Đây là catch-all route (browse, homepage, search). Ta sẽ thêm `typed_per_filter_config` cho route này để cấu hình một Token Bucket:
    -   `max_tokens`: Ngưỡng cho phép lớn nhất (ví dụ: 100-200 request).
    -   `tokens_per_fill`: Số request được hồi lại sau mỗi chu kỳ (ví dụ: 100-200).
    -   `fill_interval`: 1s.
    -   Khi vượt quá ngưỡng, Envoy sẽ trả về HTTP 429 (Too Many Requests) ngay lập tức, giảm tải cho cụm backend.

## 2. Các thay đổi dự kiến

### techx-corp-platform
#### [MODIFY] [envoy.tmpl.yaml](file:///d:/Phase3_01/Phase3-TF3-Infra-Sentinel/phase3%20-%20information/techx-corp-platform/src/frontend-proxy/envoy.tmpl.yaml)
- Thêm filter `envoy.filters.http.local_ratelimit`.
- Tách riêng route `/api/checkout` và cấu hình giới hạn tải cho route `/`.

## 3. Kế hoạch kiểm thử (Verification Plan)

- **Bước 1**: Áp dụng thay đổi cấu hình Envoy (có thể bằng cách khởi động lại/triển khai lại `frontend-proxy`).
- **Bước 2**: Sử dụng Locust web UI hoặc head-less mode để đẩy tải vượt trần (ví dụ > 500-1000 người dùng đồng thời).
- **Bước 3**: Quan sát log và metrics. Xác nhận:
  - Tỷ lệ lỗi 429 xuất hiện nhiều ở các requests liên quan đến browse/homepage.
  - Các request `/api/checkout` vẫn đạt tỉ lệ thành công cao.
  - Hệ thống không bị "cứng đơ" hay sập toàn bộ (0 requests).
- **Bước 4**: Lưu lại evidence chứng minh việc thiết lập rate limit thành công.

> [!IMPORTANT]
> Ngưỡng rate limit cho route `/` sẽ được điều chỉnh cho phù hợp dựa trên kết quả test thực tế để đảm bảo "kích hoạt shedding trước khi hệ thật sự sập". Tôi sẽ cấu hình ngưỡng token bucket bắt đầu ở mức ~150 requests/s và tinh chỉnh nếu cần.
