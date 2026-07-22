# Kế hoạch thực hiện: [MANDATE 19] Nới nút thắt bằng hiệu suất

**Task 2:** Dựa vào kết quả của Task 1, tiến hành tinh chỉnh (tuning) code hoặc cấu hình hạ tầng để nâng cao sức chịu tải (RPS đỉnh) trên cùng số lượng Node ban đầu.

## 1. Mục tiêu
- Phá vỡ (nới lỏng) nút thắt cổ chai (bottleneck) đã được xác định chính xác từ Task 1.
- Tăng **Peak RPS** và **Requests-per-node** cao hơn so với baseline của Task 1.
- Không làm sai lệch logic, không tắt validation, vẫn giữ nguyên màu xanh của SLO.
- KHÔNG thêm Node vào cụm EKS.

## 2. Phương án Tuning dự kiến (Tuỳ theo kết quả Task 1)
Sau khi có output từ Task 1, sẽ áp dụng một (hoặc kết hợp) các giải pháp sau:

*   **Kịch bản A (Nghẽn do trần HPA nhân tạo):**
    *   *Dấu hiệu:* HPA chạm mức `maxReplicas: 8`, Pod bị đè bẹp, nhưng CPU của Worker Node thực tế vẫn còn dư dả.
    *   *Cách giải quyết:* Sửa file `gitops/infrastructure/hpa-hotpath.yaml`. Tăng `maxReplicas` lên (ví dụ: 12 hoặc 16) để tận dụng hết headroom CPU của Node hiện tại.
*   **Kịch bản B (Nghẽn do cạn Connection Pool):**
    *   *Dấu hiệu:* Service `product-catalog` báo lỗi liên tục về Database connection, dù CPU vẫn còn trống. Cấu hình `MaxOpenConns(20)` bị cạn kiệt.
    *   *Cách giải quyết:* Sửa code `product-catalog/main.go`. Tăng kích thước Connection Pool một cách có kiểm soát (ví dụ: `MaxOpenConns(50)`). Đồng thời phải đối chiếu với giới hạn `max_connections` của PostgreSQL để đảm bảo không làm sập DB.
*   **Kịch bản C (Nghẽn do HPA phản ứng quá chậm):**
    *   *Dấu hiệu:* Khi tải tăng, HPA scale-up quá chậm so với tốc độ tăng tải, khiến Pod hiện tại bị ngợp trước khi Pod mới kịp Ready. Target CPU 65% chưa được tối ưu.
    *   *Cách giải quyết:* Tune lại `behavior` của HPA (tăng tốc độ scale-up) và điều chỉnh lại target metric để nhạy bén hơn.
*   **Kịch bản D (Nghẽn do thiết lập mạng lưới thiếu hiệu quả):**
    *   *Dấu hiệu:* Khởi tạo kết nối gRPC liên tục tốn tài nguyên.
    *   *Cách giải quyết:* Kiểm tra và cấu hình Keep-Alive / Connection Reuse giữa các service.

## 3. Các bước tiến hành (Execution Plan)

**Bước 1: Áp dụng cấu hình Tuning**
- Thực hiện sửa code (Go) hoặc sửa file YAML (K8s) dựa trên phương án đã chọn.
- Commit, Push và chờ quá trình CI/CD/GitOps apply thay đổi vào cụm.

**Bước 2: Re-test (Chạy lại tải)**
- Sử dụng đúng kịch bản Step-Load đã dùng ở Task 1.
- Bắn tải vào hệ thống đã được tuning.
- Giám sát SLO và Grafana xem hệ thống chịu đựng được đến đâu trước khi gãy.

**Bước 3: Nghiệm thu & Xuất báo cáo**
- Ghi nhận Peak RPS mới.
- Tính toán Requests-per-node mới.
- Đối chiếu với Baseline của Task 1 để chứng minh hiệu quả tuning.
- Hoàn thiện tài liệu và Submit PR phần Code/Config đã thay đổi.
