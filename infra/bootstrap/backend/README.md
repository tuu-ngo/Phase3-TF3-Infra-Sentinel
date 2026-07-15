# Terraform backend bootstrap

Root này mô tả ownership của S3 state bucket và DynamoDB lock table đã tồn tại trong
account `197826770971`.

Không chạy `terraform apply` trực tiếp. Trước khi root này được sử dụng, cần một thay đổi
riêng được duyệt để chọn backend riêng cho bootstrap, import các resource hiện hữu và xác
nhận plan không thay đổi cấu hình bucket/table. Đợt refactor production hiện tại không init,
import, apply hoặc ghi state cho root này.
