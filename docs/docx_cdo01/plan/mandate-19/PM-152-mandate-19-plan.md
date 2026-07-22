# Kế hoạch thực hiện: [MANDATE 19] Tìm trần thật (Breakpoint)

**Task 1:** Tăng tải dần tới khi SLO gãy để tìm ra sức chịu đựng thực tế và bottleneck của hệ thống.

## 1. Mục tiêu
- Xác định chính xác giới hạn RPS / Concurrent Users (CCU) mà tại đó hệ thống bắt đầu gãy SLO (Checkout rớt < 99%, Browse/Cart rớt < 99.5%).
- Tìm ra **đúng 1 service/tài nguyên** bị bão hòa sớm nhất (Cạn CPU, tràn Memory, cạn Connection Pool, đầy hàng đợi Kafka...).
- Tính toán chỉ số `Requests-per-node baseline`.
- Đảm bảo tính minh bạch: Lấy số liệu thật, không suy đoán.

## 2. Phương pháp & Công cụ
- **Load Generator:** Sử dụng công cụ bắn tải (Locust/K6). Sẽ cấu hình kịch bản **Step-Load** (Tăng dần số lượng user/RPS theo từng phút, ví dụ thêm 50 user mỗi phút) thay vì Spike Load (tăng đột ngột).
- **Giám sát (Monitoring):** Tập trung quan sát Grafana Dashboard (`apm-dashboard.json`).
- **Phạm vi không đổi:** KHÔNG thêm Node vào cụm EKS trong suốt quá trình test.

## 3. Các bước tiến hành (Execution Plan)

**Bước 1: Chuẩn bị & Xác nhận trạng thái ban đầu**
- Kiểm tra hệ thống đang ở trạng thái Idle (hoạt động bình thường).
- Ghi nhận số lượng Worker Node hiện tại.
- Mở sẵn Grafana, mở sẵn log của HPA (`gitops/infrastructure/hpa-hotpath.yaml`) và `product-catalog` service.

**Bước 2: Chạy Step-Load Test**
- Khởi động script bắn tải, tăng dần cường độ.
- Trong lúc tăng tải, theo dõi sát sao:
  1. HPA của các service hot-path đã scale lên mức tối đa (maxReplicas = 8) chưa?
  2. CPU và Memory của các pod đang ở mức bao nhiêu %?
  3. Connection Pool đến Database của `product-catalog` có chạm mức 20 (`MaxOpenConns(20)` trong `main.go`) không?
  4. Có xuất hiện lỗi 503, 504 hoặc Timeout ở service nào không?

**Bước 3: Dừng tải & Phân tích điểm gãy (Breakpoint)**
- Khi quan sát thấy đường p99 latency trên Grafana vượt ngưỡng cho phép, hoặc Error Rate vượt 1%, lập tức dừng công cụ bắn tải.
- Ghi nhận lại mức **RPS Đỉnh (Peak RPS)** ngay trước thời điểm gãy.
- Chụp ảnh màn hình Grafana tại thời điểm gãy làm bằng chứng (Evidence).
- Truy tìm nguyên nhân gốc rễ (Root Cause): Service nào đạt 100% CPU trước? Hoặc service nào báo lỗi cạn connection trước?

**Bước 4: Tính toán Baseline & Xuất báo cáo**
- Công thức: `Requests-per-node = Peak RPS / Tổng số Node`.
- Viết file tài liệu báo cáo: Tổng hợp RPS đỉnh, Service nghẽn đầu tiên, Bằng chứng Grafana, và Baseline. Nộp báo cáo làm tiền đề cho Task 2.
