# Yêu cầu Kỹ thuật & Giải pháp: Mandate 12 - Kiểm toán không thể bị đánh bại (Audit Anti-Defeat)

**Dự án:** Phase 3 - Infra Sentinel
**Nhóm phụ trách:** Task Force 3 (Auditability)
**Tài liệu tham chiếu:** `MANDATE-12-audit-anti-defeat-tf3.md`

---

## 1. Mục tiêu (Objective)
Xây dựng một hệ thống Audit Trail (lưu vết kiểm toán) hoàn hảo, chịu được các kịch bản tấn công nhắm trực tiếp vào hệ thống log. Đảm bảo kẻ tấn công không thể làm hệ thống bị "mù", bị "hụt" dữ liệu quan trọng, hay giả mạo nội dung file log nhằm xóa dấu vết.

---

## 2. Yêu cầu Hệ thống (System Requirements)

### 2.1. Yêu cầu chống "Làm mù" (No Blind Window)
*   **REQ-1.1:** Không một user hay role nào (kể cả Administrator của hệ thống) được phép vô hiệu hóa, tạm dừng hoặc xóa cấu hình hệ thống ghi log.
*   **REQ-1.2:** Mọi hành vi cố tình gọi API để tắt hệ thống log (`StopLogging`, `DeleteTrail`, v.v.) phải bị chặn (Access Denied).
*   **REQ-1.3:** Khi có hành vi cố tình tắt log, hệ thống phải kích hoạt báo động ngay lập tức và gửi thông báo về kênh vận hành (ví dụ: Slack, Email), chỉ rõ ai đã thực hiện và lúc mấy giờ.

### 2.2. Yêu cầu chống "Làm hụt" (Close Coverage Gap)
*   **REQ-2.1:** Hệ thống phải ghi lại vết không chỉ các hành động quản trị (Management Events) mà cả các hành động tương tác với dữ liệu (Data Events).
*   **REQ-2.2:** Mọi hành vi ĐỌC (Read) đối với các kho lưu trữ dữ liệu nhạy cảm (S3 Buckets) phải được ghi log đầy đủ (Ai đã đọc file nào).
*   **REQ-2.3:** Mọi hành vi truy xuất khóa bí mật, mật khẩu (Secrets) cũng phải được ghi nhận (Ai đã lấy secret nào).

### 2.3. Yêu cầu chống "Làm mỏng / Chỉnh sửa" (Log Integrity Validation)
*   **REQ-3.1:** Phải có cơ chế xác minh toàn vẹn file log dựa trên mật mã học (Cryptographic Hash / Digest).
*   **REQ-3.2:** Hệ thống phải cung cấp công cụ/câu lệnh để kiểm tra ngay lập tức xem chuỗi log có bị thêm, xóa hay sửa đổi bất hợp pháp hay không.

### 2.4. Yêu cầu về thời gian lưu trữ & Ngân sách (Retention & Cost)
*   **REQ-4.1:** Log phải được lưu trữ với khoảng thời gian đủ dài để điều tra các cuộc tấn công dai dẳng (APT) theo tiêu chuẩn bảo mật của tổ chức (VD: 90 ngày truy cập nóng, 1 năm lưu trữ lạnh).
*   **REQ-4.2:** Giải pháp phải nằm trong ngân sách cho phép (khoảng ~$300/tuần/TF).
*   **REQ-4.3:** Không làm ảnh hưởng đến hiệu năng của Storefront và hệ thống vận hành.

---

## 3. Gợi ý Giải pháp Kiến trúc (Dành cho môi trường AWS)

### Giải pháp cho REQ-1 (Chống làm mù)
*   **Sử dụng AWS Organizations & SCPs:** Tạo Service Control Policies (SCP) áp dụng cho account của TF4, explicitly "Deny" các action: `cloudtrail:StopLogging`, `cloudtrail:DeleteTrail`, `cloudtrail:UpdateTrail`. Điều này chặn cả quyền root/admin của account đó.
    *   **Tại sao chọn:** SCP áp đặt chính sách ở cấp độ tổ chức (Organizations level), có độ ưu tiên cao hơn mọi quyền IAM nội bộ. Ngay cả tài khoản Root của account ứng dụng cũng không thể vượt qua, khóa chặn hoàn toàn lỗ hổng lạm quyền để tắt hệ thống kiểm toán.
*   **Sử dụng AWS EventBridge + SNS:** Tạo một EventBridge Rule lắng nghe các CloudTrail event. Nếu event name là `StopLogging` hoặc `DeleteTrail` (kể cả khi API bị Access Denied), lập tức trigger gửi message vào Amazon SNS Topic, từ đó đẩy thông báo về Slack/Email của team SOC.
    *   **Tại sao chọn:** Đây là kiến trúc tự động hoá serverless tiêu chuẩn của AWS. Tốc độ phản hồi cực nhanh (near real-time), cấu hình đơn giản, dễ tích hợp với các công cụ cảnh báo (Slack/PagerDuty) mà không tốn chi phí vận hành server.

### Giải pháp cho REQ-2 (Chống làm hụt)
*   **Bật CloudTrail Data Events:** Trong cấu hình của CloudTrail (hiện tại), bổ sung thêm phần **Data Events**.
    *   **Tại sao chọn:** Mặc định CloudTrail chỉ ghi nhận các API quản trị (Control plane). Để bắt được các hành vi truy xuất hay trích xuất dữ liệu trực tiếp (Data plane) như `GetObject`, việc bật Data Events là tính năng duy nhất và thiết yếu.
*   **Tối ưu chi phí bằng ARN Filtering:** Tránh bật Data Event cho *tất cả* S3 bucket. Hãy chỉ định đích danh (ARN) của Bucket chứa dữ liệu nhạy cảm cần monitor, và bật Data Events cho tài nguyên `AWS::SecretsManager::Secret` (hoặc `AWS::SSM::Parameter` nếu dùng Parameter Store).
    *   **Tại sao chọn:** Phí ghi nhận Data Events được tính dựa trên số lượng event sinh ra và khá đắt đỏ. Phương pháp lọc ARN đích danh giúp hệ thống tập trung giám sát các tài nguyên trọng yếu, từ đó đáp ứng nghiêm ngặt được ràng buộc về ngân sách của dự án (~$300/tuần/TF).

### Giải pháp cho REQ-3 (Chống sửa đổi log)
*   **Bật CloudTrail Log File Validation:** Vào CloudTrail config, bật tính năng *Log file validation*. Mỗi khi log được đẩy về S3, AWS sẽ tạo thêm một file digest chứa mã SHA-256 hash của file log đó. Chuỗi digest này liên kết với nhau bằng Public/Private Key do AWS quản lý, không ai có thể giả mạo.
    *   **Tại sao chọn:** Đây là tính năng native giải quyết trực tiếp yêu cầu chứng minh bằng mật mã học (cryptographic proof). Nó tự động thực hiện và cho phép dùng ngay lệnh CLI có sẵn để chứng minh tính nguyên vẹn của log trước Mentor, giảm thiểu hoàn toàn công sức tự xây dựng cơ chế hashing thủ công.

### Giải pháp cho REQ-4 (Lưu trữ an toàn)
*   Sử dụng một **Centralized S3 Bucket** chỉ dùng cho mục đích Audit.
    *   **Tại sao chọn:** Việc cô lập (isolate) hoàn toàn môi trường lưu log ra khỏi account đang chạy ứng dụng đảm bảo rằng nếu account ứng dụng bị tấn công (compromised), hacker cũng không thể với tay được tới kho log đang nằm ở account khác.
*   Thiết lập **S3 Lifecycle Rule**: Chuyển log sang Glacier sau 90 ngày và xóa (Expire) sau 1 năm hoặc 3 năm.
    *   **Tại sao chọn:** Thiết kế này cân bằng hoàn hảo giữa hiệu năng điều tra (truy xuất nhanh log nóng trong 90 ngày đầu) và chi phí (chuyển sang Glacier lưu trữ lạnh dài hạn với giá rẻ).
*   Kế thừa giải pháp Mandate #4: Bật **S3 Object Lock (Compliance mode)** trên S3 bucket này.
    *   **Tại sao chọn:** Object Lock ở chế độ Compliance (WORM - Write Once Read Many) là bức tường thành vững chắc nhất. Nó chặn hoàn toàn việc xóa hoặc sửa file log trước thời hạn retention, kể cả khi người yêu cầu xóa có quyền tối cao (Root/Admin), qua đó thỏa mãn trọn vẹn tiêu chí "không thể xóa" của Mandate 4 và 12.

---

## 4. Kế hoạch Nghiệm thu (Testing / Validation Plan)

Khi bàn giao, Team sẽ mời Mentor thực hiện 3 bài test sau để chứng minh Audit không bị đánh bại:

1.  **Test làm mù:**
    *   Mentor dùng tài khoản quyền cao nhất, chạy lệnh: `aws cloudtrail stop-logging --name <trail-name>`
    *   **Kỳ vọng:** Terminal báo `AccessDeniedException`. Cùng lúc đó, Slack nổ cảnh báo: `[ALERT] User X attempted to StopLogging on CloudTrail at <time>`.
2.  **Test làm hụt:**
    *   Mentor dùng tài khoản bất kỳ gọi lệnh: `aws s3 cp s3://<sensitive-bucket>/secret-data.txt .` hoặc `aws secretsmanager get-secret-value --secret-id <secret-name>`
    *   **Kỳ vọng:** Nhóm query Athena (hoặc CloudWatch Logs) trích xuất được ngay dòng log ghi lại API Call vừa rồi, chỉ rõ ARN của user và IP thực hiện.
3.  **Test làm mỏng / sửa đổi:**
    *   Nhóm bật Terminal và chạy lệnh xác minh tại chỗ:
        `aws cloudtrail validate-logs --trail-arn <trail-arn> --start-time 2026-07-17T00:00:00Z`
    *   **Kỳ vọng:** AWS trả về thông báo các file log đều `Valid` (hợp lệ), chứng minh không có sự kiện nào bị sửa/xóa/nuốt chửng.
