# AIO Bedrock Rollout

Runbook này mô tả cách bật AI runtime thật cho `product-reviews` bằng AWS Bedrock theo thứ tự an toàn, hạn chế rủi ro với hệ thống đang chạy.

## Objective

- chuyển `product-reviews` từ mock/OpenAI-compatible path sang Bedrock path
- giới hạn quyền Bedrock chỉ cho `product-reviews`
- rollout theo thứ tự có thể kiểm chứng và rollback được

## Scope

Runbook này chỉ áp dụng cho phần AI summary/Q&A nằm trong service `product-reviews`.

Không áp dụng cho:
- frontend riêng
- các service khác ngoài `product-reviews`
- thay đổi ngoài phạm vi Bedrock runtime, service account và image rollout

## Prerequisites

Các điều kiện sau phải có trước khi bật runtime:

- code hỗ trợ Bedrock đã được merge vào `main`
- chart đã hỗ trợ service account riêng theo component
- Terraform đã có resource tạo IRSA role `product-reviews-bedrock`
- image `product-reviews` mới đã được build và push lên ECR
- digest/tag image dự kiến rollout đã được xác minh

## Why The Rollout Is Split

- Production pin `product-reviews` qua `imageOverride` trong `phase3 - information/deploy/values-prod.yaml`.
- `values-aio-llm.yaml` đưa vào runtime các biến môi trường dành cho Bedrock.
- Nếu enable file values này khi workload vẫn đang dùng image cũ, pod có thể khởi động với cấu hình không tương thích.

Vì lý do đó, rollout cần đi theo thứ tự:
- chuẩn bị code/chart/infra
- xác nhận IRSA tồn tại
- build/push image mới
- chỉ sau đó mới enable runtime trong GitOps

## Deployment Sequence

1. Merge phần preparation vào `main`.

Preparation bao gồm:
- code `product-reviews` hỗ trợ Bedrock
- chart hỗ trợ service account riêng
- Terraform khai báo IRSA role cho `product-reviews`

2. Apply Terraform production.

Sau bước này cần xác nhận role sau đã tồn tại:
- `techx-corp-tf3-product-reviews-bedrock`

Output mong đợi:
- `product_reviews_bedrock_role_arn`

3. Build và push image mới cho `product-reviews`.

Yêu cầu:
- image phải được push lên ECR production
- digest/tag phải được ghi nhận lại để pin vào `values-prod.yaml`

4. Enable runtime trong GitOps.

Hai thay đổi bắt buộc:
- cập nhật `phase3 - information/deploy/values-prod.yaml` để `product-reviews` dùng image mới
- thêm `../deploy/values-aio-llm.yaml` vào `gitops/apps/techx-corp.yaml`

5. Chờ sync và rollout hoàn tất trên cluster.

## Validation

Sau rollout cần xác minh tối thiểu:

- deployment `product-reviews` đạt `2/2 Available`
- pod `product-reviews` ở trạng thái `Running`
- service account của pod là `product-reviews-bedrock`
- service account có annotation:
  `eks.amazonaws.com/role-arn: arn:aws:iam::197826770971:role/techx-corp-tf3-product-reviews-bedrock`
- image thực tế của pod khớp digest vừa rollout
- env runtime có:
  - `LLM_PROVIDER=bedrock`
  - `LLM_MODEL=amazon.nova-lite-v1:0`
  - `AWS_REGION=us-east-1`
- gRPC call `AskProductAIAssistant` trả kết quả hợp lệ
- câu hỏi ngoài phạm vi trả về thông điệp out-of-scope
- health check của `product-reviews` vẫn phụ thuộc DB, không trả xanh giả

## Rollback

Nếu rollout lỗi, rollback theo thứ tự ít rủi ro nhất:

1. Revert thay đổi runtime trong GitOps:
- bỏ `../deploy/values-aio-llm.yaml` khỏi `gitops/apps/techx-corp.yaml`
- đổi `product-reviews.imageOverride` về image/digest trước đó trong `values-prod.yaml`

2. Chờ ArgoCD sync lại và xác nhận pod quay về trạng thái ổn định.

3. Chỉ rollback Terraform nếu có lý do rõ ràng.

Thông thường không cần xóa ngay IRSA role chỉ vì runtime rollback.

## Notes

- Không cấp quyền Bedrock vào service account global `techx-corp`.
- Không enable `values-aio-llm.yaml` trước khi image mới sẵn sàng.
- Không patch tay production nếu chưa xác nhận image/tag/runtime config.
- Với thay đổi liên quan runtime production, ưu tiên xác minh cả ở mức artifact, manifest render và cluster runtime thực tế.
