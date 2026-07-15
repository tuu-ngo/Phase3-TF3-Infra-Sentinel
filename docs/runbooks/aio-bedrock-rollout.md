# AIO Bedrock Rollout

Runbook này dùng để bật AI thật cho `product-reviews` mà không làm ảnh hưởng hệ thống đang chạy.

## Mục tiêu

- `product-reviews` gọi AWS Bedrock thay vì mock `llm`
- chỉ `product-reviews` có quyền Bedrock
- không rollout `values-aio-llm.yaml` trước khi image mới và IRSA sẵn sàng

## Vì sao phải rollout theo nhiều bước

- Production hiện pin `product-reviews` bằng `imageOverride` trong `phase3 - information/deploy/values-prod.yaml`.
- `values-aio-llm.yaml` mới dùng env theo đường Bedrock.
- Nếu bật file values này khi pod vẫn đang chạy image cũ, pod có thể fail vì code cũ còn kỳ vọng biến môi trường theo đường mock/OpenAI.

## Trình tự an toàn

1. Merge PR chuẩn bị hạ tầng/chart:
   - code `product-reviews` hỗ trợ Bedrock
   - chart hỗ trợ service account riêng theo component
   - Terraform tạo IRSA role `product-reviews-bedrock`

2. Apply Terraform production:
   - lấy output `product_reviews_bedrock_role_arn`
   - xác nhận role đã tồn tại trước khi enable runtime

3. Build và push image mới cho `product-reviews`
   - dùng workflow `build-push-ecr.yml`
   - ghi lại tag/digest mới được push

4. Tạo PR enable runtime:
   - cập nhật `phase3 - information/deploy/values-prod.yaml` với `product-reviews.imageOverride.tag` và `digest` mới
   - thêm `../deploy/values-aio-llm.yaml` vào `gitops/apps/techx-corp.yaml`

5. Verify sau deploy:
   - pod `product-reviews` dùng service account `product-reviews-bedrock`
   - pod lên `Ready`
   - review AI trả kết quả thật
   - health check của `product-reviews` vẫn phụ thuộc DB, không trả xanh giả

## Không khuyến nghị

- Không cấp Bedrock vào service account global `techx-corp`
- Không enable `values-aio-llm.yaml` trước khi image mới sẵn sàng
- Không patch tay production trước khi kiểm tra image/tag/runtime config
