# Mandate 12 — biến bổ sung cho module audit-detection của Mandate 11.
# Giữ default bằng đúng giá trị M11 đang chạy để module không đổi hành vi
# khi caller chưa truyền giá trị mới.

variable "trail_object_lock_mode" {
  description = "Default Object Lock mode cho object CloudTrail mới. Không áp hồi tố cho object đã ghi."
  type        = string
  default     = "GOVERNANCE"

  validation {
    condition     = contains(["GOVERNANCE", "COMPLIANCE"], var.trail_object_lock_mode)
    error_message = "trail_object_lock_mode must be GOVERNANCE or COMPLIANCE."
  }
}

variable "trail_object_lock_days" {
  description = "Default Object Lock duration cho object CloudTrail mới."
  type        = number
  default     = 14

  validation {
    condition     = var.trail_object_lock_days >= 1
    error_message = "trail_object_lock_days must be positive."
  }
}

variable "s3_data_event_arns" {
  description = "Approved S3 Object ARN scopes. Toàn bucket hoặc prefix đều phải kết thúc bằng /."
  type        = list(string)
  default     = []

  validation {
    condition = alltrue([
      for arn in var.s3_data_event_arns :
      can(regex("^arn:aws:s3:::[^/]+/.*$", arn)) && endswith(arn, "/")
    ])
    error_message = "Each S3 Object ARN must be valid and end with /."
  }
}

# Default false để module vẫn dùng lại được ở instance không tạo trail hoặc
# chưa cần data events. Production truyền true: khi đó plan FAIL nếu danh sách
# rỗng, thay vì apply âm thầm một trail không ghi GetObject.
variable "require_s3_data_event_coverage" {
  description = "Bắt plan thất bại nếu s3_data_event_arns rỗng. Mandate 12 yêu cầu true ở production."
  type        = bool
  default     = false
}

# Topic alert được mã hoá bằng CMK, nên CloudWatch phải gọi được KMS thì alarm
# action mới publish vào topic. Thiếu quyền này alarm fail âm thầm: alarm vẫn
# chuyển ALARM, SNS không nhận gì, không có lỗi nào nổi lên.
#
# Default false vì chỉ instance nào thực sự có alarm trỏ vào topic mới cần —
# instance us-east-1 dùng topic trực tiếp từ Lambda, không qua alarm.
variable "cloudwatch_alarm_publisher_enabled" {
  description = "Cấp cho cloudwatch.amazonaws.com quyền dùng audit KMS key để publish alarm vào topic alert."
  type        = bool
  default     = false
}

# Resource audit plane nằm ngoài module — heartbeat M12 và các thứ nó kéo theo
# (schedule rule, 2 alarm, topic fallback). Module không biết tên chúng nên
# caller phải khai, nếu không event nhóm 7 nhắm vào heartbeat sẽ bị coi là
# "không phải audit plane" và bỏ qua.
variable "additional_audit_plane_keywords" {
  description = "Tiền tố/tên resource audit plane ngoài module, so khớp lowercase substring với target của event nhóm 7."
  type        = list(string)
  default     = []
}
