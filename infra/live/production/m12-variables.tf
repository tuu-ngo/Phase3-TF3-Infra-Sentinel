# Mandate 12 — biến ở tầng production root.

# Mỗi giá trị phải kết thúc bằng "/" (toàn bucket dùng dạng arn:aws:s3:::bucket/)
# và khớp 1:1 với hàng APPROVED trong m12-coverage matrix.
#
# Default rỗng để plan chạy được khi review PR. Đây KHÔNG phải trạng thái hoàn
# tất: khi rỗng, trail không ghi S3 data event và Mandate 12 sẽ trượt đòn
# "làm hụt" (T03). Phải điền giá trị đã được data owner duyệt trước apply.
variable "audit_detection_s3_data_event_arns" {
  description = "Mandate 12: exact S3 Object ARN scope cho trail M11 hiện hữu."
  type        = list(string)
  default     = []

  validation {
    condition = alltrue([
      for arn in var.audit_detection_s3_data_event_arns :
      can(regex("^arn:aws:s3:::[^/]+/.*$", arn)) && endswith(arn, "/")
    ])
    error_message = "Each approved S3 Object ARN must be valid and end with /."
  }
}

variable "audit_detection_trail_object_lock_mode" {
  description = "Mandate 12: Object Lock mode cho object CloudTrail mới. COMPLIANCE không thể rút ngắn, kể cả bằng root."
  type        = string
  default     = "COMPLIANCE"

  validation {
    condition     = contains(["GOVERNANCE", "COMPLIANCE"], var.audit_detection_trail_object_lock_mode)
    error_message = "audit_detection_trail_object_lock_mode must be GOVERNANCE or COMPLIANCE."
  }
}

variable "audit_detection_trail_object_lock_days" {
  description = "Mandate 12: số ngày Object Lock cho object CloudTrail mới. Mandate yêu cầu tối thiểu 365."
  type        = number
  default     = 365

  validation {
    condition     = var.audit_detection_trail_object_lock_days >= 365
    error_message = "Mandate 12 requires at least 365 days of Object Lock retention."
  }
}
