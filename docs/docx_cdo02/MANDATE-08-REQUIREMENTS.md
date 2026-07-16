# Requirement Document: Mandate 08 - Managed Services Migration

**Dự án:** Phase 3 - TechX Corp
**Chủ đề:** Đưa toàn bộ tầng dữ liệu lên AWS Managed Service (Mandate 08)
**Trạng thái:** Bản dự thảo (Draft) chờ PM duyệt

---

## 1. Bối cảnh (Background)
Hệ thống hiện tại đang tự lưu trữ (self-host) 3 hệ thống dữ liệu cốt lõi bên trong Kubernetes cluster (chạy dưới dạng pod):
- **PostgreSQL** (Database)
- **Valkey / Redis** (Cache)
- **Kafka** (Message Queue)

Việc tự vận hành mang lại nhiều rủi ro: Không có cơ chế backup tự động, thiếu cấu hình độ sẵn sàng cao (Multi-AZ), dữ liệu không được mã hóa đạt chuẩn, và tốn nhiều công sức để bảo trì. 

## 2. Mục tiêu (Objective)
Di chuyển toàn bộ 3 hệ thống dữ liệu trên sang các dịch vụ quản lý hoàn toàn của AWS (Managed Services) nhằm tăng cường **Độ tin cậy (Reliability)**, đảm bảo **Bảo mật (Security)** và **Tối ưu chi phí (Cost Optimization)**.

---

## 3. Yêu cầu Kỹ thuật (Technical Requirements)

### 3.1. Dịch vụ Đích (Target Services)
*   **PostgreSQL** bắt buộc phải chuyển sang **Amazon RDS**.
*   **Valkey (Redis)** bắt buộc phải chuyển sang **Amazon ElastiCache**.
*   **Kafka** bắt buộc phải chuyển sang **Amazon MSK**.
*   **Tiêu chí:** Kết thúc quá trình, KHÔNG còn bất kỳ pod database, cache, hay queue nào chạy tự host bên trong Kubernetes cluster.

### 3.2. Yêu cầu Migration (Dịch chuyển dữ liệu)
*   **Không gián đoạn (Zero-downtime):** Ứng dụng phải hoạt động liên tục, khách hàng không được phép nhận ra sự thay đổi.
*   **Cam kết SLO:** Service Level Objective (SLO) phải luôn được giữ ở mức **≥ 99%** trong toàn bộ quá trình chuyển đổi (cutover).
*   **Toàn vẹn dữ liệu:** Schema và dữ liệu seed hiện tại phải được nạp sang Managed Services đầy đủ. Các ứng dụng nội bộ phải đọc/ghi chuẩn xác như trước.

### 3.3. Yêu cầu Bảo mật (Security Requirements)
*   **Encryption In-transit:** Toàn bộ traffic tới RDS, ElastiCache, MSK phải được mã hóa qua TLS.
*   **Encryption At-rest:** Dữ liệu lưu trữ phải được mã hóa.
*   **Quản lý Secrets:** Các thông tin nhạy cảm (Credentials, Mật khẩu DB, Auth tokens) phải được lưu trong **AWS Secrets Manager**. Tuyệt đối không để lộ dưới dạng plaintext trong manifest hay biến môi trường.
*   **Private Endpoints:** Hệ thống Database/Cache/Queue chỉ được truy cập nội bộ (Private), tuyệt đối không phơi (expose) ra Public internet.

### 3.4. Tối ưu chi phí (Cost Awareness)
*   Lựa chọn cấu hình phần cứng (Right-sizing) phù hợp.
*   Đưa ra tài liệu giải thích rõ lý do chọn cấu hình **Multi-AZ** hay **Single-AZ**.
*   Tổng chi phí AWS cho toàn bộ thay đổi này phải nằm trong giới hạn ngân sách: **~$300/tuần**.

---

## 4. Ràng buộc Hệ thống (Constraints)
*   Cổng Storefront vẫn phải giữ ở chế độ công khai (Public).
*   Cổng vận hành nội bộ vẫn phải giữ ở chế độ riêng tư (Private) (Theo chuẩn Directive #1).
*   Hệ thống Feature Flag (`flagd`) không được phép vô hiệu hóa hay can thiệp phá vỡ.

---

## 5. Tiêu chí Nghiệm thu (Acceptance Criteria)
*   [ ] 3 hệ thống dữ liệu (RDS, ElastiCache, MSK) đã hoạt động trên AWS ở private subnet.
*   [ ] Ứng dụng đã được cập nhật cấu hình kết nối thành công tới endpoint mới (thông qua Secrets Manager).
*   [ ] Các Pod datastore cũ (postgresql, valkey, kafka) đã bị xóa bỏ hoàn toàn khỏi cluster.
*   [ ] Có bằng chứng (Log/Screenshot) chứng minh **Data Parity** (tổng số lượng row, record, key khớp nhau giữa cũ và mới).
*   [ ] Có **Rollback Plan** rõ ràng được đính kèm.
