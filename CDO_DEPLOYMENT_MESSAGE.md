# Yêu Cầu Triển Khai Hệ Thống (CDO Deploy Request)

Chào anh em CDO,

Bên AIO/AIE1 đã hoàn thành việc nâng cấp dịch vụ `product-reviews` để kết nối trực tiếp với AWS Bedrock (boto3 Converse API) thay vì đi qua LiteLLM proxy cũ nhằm tối ưu độ trễ và tăng tính ổn định.

Để deploy phiên bản mới này lên EKS, nhờ anh em CDO hỗ trợ một số điểm sau và merge code từ branch **`feature/product-review`** vào `main`:

### 1. Build lại Docker Image:
* Đã cập nhật file `requirements.txt` (thêm `boto3` và `tenacity`) và source code của `product-reviews`.
* Nhờ anh em chạy lại pipeline CI/CD hoặc chạy script **`phase3 - information/deploy/build-push-images.sh`** để đóng gói và push image mới lên registry.

### 2. Cập nhật Helm Values:
* Cấu hình môi trường mới đã được push tại tệp **`phase3 - information/deploy/values-aio-llm.yaml`**.
* Đã bổ sung các biến môi trường: `LLM_PROVIDER: bedrock`, `LLM_MODEL: amazon.nova-lite-v1:0` và `AWS_REGION: us-east-1`. Nhờ anh em dùng file này khi chạy `helm upgrade`.

### 3. Cấp quyền truy cập AWS Bedrock (Quan trọng):
* Pod của `product-reviews` trên EKS cần có quyền gọi Bedrock (bao gồm cả mô hình tóm tắt `amazon.nova-lite-v1:0` và mô hình giám khảo/judge `amazon.nova-micro-v1:0`). Nhờ anh em cấu hình theo 1 trong 2 cách:
  * **Cách 1 (Khuyên dùng):** Gắn IAM Policy cho ServiceAccount của Pod `product-reviews` trên EKS với các quyền:
    * `bedrock:InvokeModel`
    * `bedrock:InvokeModelWithResponseStream`
    *(Lưu ý: AWS IAM xác thực các API Converse qua hành động `InvokeModel`, chứ không có hành động `bedrock:Converse`).*
  * **Cách 2:** Nếu chưa bật IRSA, nhờ anh em tạo Kubernetes Secret chứa `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` (có quyền gọi 2 model Bedrock trên) rồi map vào `envOverrides` của Pod.

Cảm ơn anh em!
