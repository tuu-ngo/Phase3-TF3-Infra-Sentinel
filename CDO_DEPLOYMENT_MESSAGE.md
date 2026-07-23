# Yêu Cầu Triển Khai Hệ Thống (CDO Deploy Request) - CẬP NHẬT BIGUPDATE SPRINT 3

Chào anh em CDO,

Bên AIO/AIE1 đã hoàn thành nâng cấp dịch vụ `product-reviews` kết nối trực tiếp với AWS Bedrock, đồng thời hoàn thiện hệ thống Caching 2 tầng, bộ điều khiển sự cố (Actuator) phục vụ kịch bản Closed-Loop Mitigation.

Dưới đây là các đầu việc chi tiết nhờ anh em CDO hỗ trợ triển khai khi deploy phiên bản mới này lên EKS:

### 1. Database Migration (Quan trọng - thực hiện trước khi deploy app):
* Dịch vụ cần bổ sung cấu trúc dữ liệu mới để lọc review sạch. Nhờ anh em chạy tệp migration:
  * [migration.sql](file:///C:/Users/ASUS/OneDrive/Obsidian%20Vault/XBrain-Phase3/Phase3-TF3-Infra-Sentinel/phase3%20-%20information/techx-corp-platform/src/product-reviews/migration.sql): Thêm cột `is_safe` (mặc định `TRUE`) và index `productreviews_prod_safe_idx` vào bảng `reviews.productreviews`.
* Chạy worker đồng bộ dữ liệu cũ:
  * Chạy tệp [db_migration_worker.py](file:///C:/Users/ASUS/OneDrive/Obsidian%20Vault/XBrain-Phase3/Phase3-TF3-Infra-Sentinel/phase3%20-%20information/techx-corp-platform/src/product-reviews/db_migration_worker.py) để tự động quét toàn bộ review cũ và đánh dấu `is_safe = FALSE` nếu vi phạm bộ lọc Regex Guardrail. Chạy độc lập ngoài request path để tránh ảnh hưởng hệ thống.

### 2. Cấu hình Redis Caching:
* Hệ thống đã tích hợp Caching 2 tầng (Redis Real-time Cache + Postgres).
* Nhờ anh em kiểm tra kết nối gRPC/HTTP tới Valkey/Redis của cluster, đảm bảo dịch vụ nhận được các biến môi trường kết nối Redis (đã cấu hình mặc định tự động nhận diện, hỗ trợ TLS `rediss://`).

### 3. Cổng điều khiển Sự cố (Actuator) & Telemetry (MANDATE #22):
* **Actuator:** Dịch vụ tự động lắng nghe Redis key `product_reviews:fallback_override`. Khi AIOps Detector set key này bằng `true` hoặc `1`, dịch vụ sẽ lập tức bypass hoàn toàn Bedrock và chuyển sang chế độ fallback.
* **Failure Injection Mode:** Nhận diện thông qua flag `llmRateLimitError` từ flagd để giả lập lỗi kết nối LLM (chế độ phục vụ test replay sự cố).
* **Telemetry Metrics:** Xuất Prometheus metric `app_ai_fallback_total` để monitor lỗi kết nối LLM.

### 4. Build lại Docker Image:
* Đã cập nhật file `requirements.txt` (bổ sung `redis` bên cạnh `boto3` và `tenacity`) và toàn bộ mã nguồn liên quan.
* Nhờ anh em chạy script [build-push-images.sh](file:///C:/Users/ASUS/OneDrive/Obsidian%20Vault/XBrain-Phase3/Phase3-TF3-Infra-Sentinel/phase3%20-%20information/deploy/build-push-images.sh) để build multi-arch image mới (`1.0-product-reviews`) và push lên registry.

### 5. Helm Upgrade & Phân quyền AWS Bedrock (IRSA):
* **IAM Policy:** Đảm bảo ServiceAccount `techx-corp` trong namespace `techx-corp` được gắn IAM Role có quyền gọi Bedrock:
  * `bedrock:InvokeModel`
  * `bedrock:InvokeModelWithResponseStream`
  * `bedrock:ApplyGuardrail`
* **Helm Values:** Sử dụng cấu hình cập nhật tại [values-aio-llm.yaml](file:///C:/Users/ASUS/OneDrive/Obsidian%20Vault/XBrain-Phase3/Phase3-TF3-Infra-Sentinel/phase3%20-%20information/deploy/values-aio-llm.yaml) (đã tích hợp ServiceAccount role-arn annotation).

Cảm ơn anh em!
