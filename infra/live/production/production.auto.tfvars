eks_admin_principal_arns = [
  "arn:aws:iam::197826770971:user/cdo-2-admin-team",
]

edge_phase       = "private"
private_alb_name = "techx-tf3-frontend-internal"

enable_cloudflare_access        = true
cloudflare_account_id           = "4903f08491f403370e1a2ae9c8aee84e"
cloudflare_zone_id              = "b711c7ecbcb4efb9d909de520330f0bb"
cloudflare_zone_name            = "arthur-ngo.org"
cloudflare_tunnel_hostname      = "kubectl.arthur-ngo.org"
cloudflare_allowed_email_domain = ""
cloudflare_allowed_emails = [
  "hiimtuu@gmail.com",
  "tutc.work@gmail.com",
  "trongtanaws@gmail.com",
  # Mentors — SSO access tới Grafana/Jaeger/ArgoCD UI qua Cloudflare Zero Trust (REL-17).
  "nghia.huynh@techxcorp.com",
  "toan.le@techxcorp.com",
  "khanh.nguyen@techxcorp.com",
  "namhong.ta@techxcorp.com",
]

# Mandate #8 — bật tầng datastore managed (RDS/ElastiCache/MSK).
# Đặt = true để state khớp hạ tầng thật; nếu để default false, plan sau sẽ đòi XOÁ 3 store.
enable_managed_datastores = true

audit_detection_email_subscriptions = [
  "dophuc776@gmail.com",
  "huutai.ngo2409@gmail.com",
  "nguyenthimen190504@gmail.com",
  "nvtvlog234@gmail.com",
  "tranduc.357cc@gmail.com",
  "haileab542@gmail.com"
]

audit_detection_additional_human_principal_arns = [
  "arn:aws:iam::197826770971:user/aio2-admin-team",
  "arn:aws:iam::197826770971:user/cdo-2-admin-team",
  "arn:aws:iam::197826770971:user/cdo-admin-team",
  "arn:aws:iam::197826770971:user/hieu-AdminAccess",
  "arn:aws:iam::197826770971:user/KietBE",
  "arn:aws:iam::197826770971:user/mentor-mandate-reviewer",
  "arn:aws:iam::197826770971:user/Thao",
]

# CẢNH BÁO (Mandate 12): principal trong danh sách này được router bỏ qua ở các
# nhóm KHÔNG critical. Sau M12, critical_group_numbers = [1,2,3,4,7,8] nên
# StopLogging, leo thang quyền IAM, tamper alert plane và boundary/OIDC vẫn luôn
# cảnh báo kể cả với principal ở đây. Phần còn bị bỏ qua là group 5 (đọc secret)
# và group 6 (hành động huỷ hoại).
#
# `gitlab-ci-deployer` là IAM user admin, chưa MFA, còn access key dài hạn đang
# hoạt động. Gỡ khỏi danh sách này + rotate key là việc của phase IAM hardening
# (xem docs/mandate-12-execution-plan.md §9). KHÔNG gỡ trong PR foundation vì
# cần owner pipeline GitLab xác nhận downtime window trước.
audit_detection_additional_allowed_automation_principal_arns = [
  "arn:aws:iam::197826770971:user/gitlab-ci-deployer",
]

# Mandate 12 — retention.
# Lifecycle (400) phải DÀI HƠN Object Lock (365): object bị Compliance-lock
# không xoá được, lifecycle ngắn hơn sẽ fail âm thầm. Module có precondition
# chặn cấu hình sai. Lưu ý: 400 ngày áp cho CẢ object hiện có chưa bị xoá, nên
# dung lượng lưu trữ tăng ngay sau apply — cần cost approval trước.
audit_detection_trail_s3_retention_days = 400

# Mandate 12 — S3 data events.
# BẮT BUỘC điền trước apply, lấy đúng giá trị đã ký trong coverage matrix.
# Mỗi ARN phải kết thúc bằng "/". Toàn bucket dùng dạng arn:aws:s3:::bucket/
# Để rỗng = trail KHÔNG ghi S3 data event = trượt đòn "làm hụt" (T03).
# Không dùng bucket audit archive (tạo vòng lặp logging; module có precondition chặn).
# audit_detection_s3_data_event_arns = [
#   "arn:aws:s3:::<approved-bucket>/<approved-prefix>/",
# ]
