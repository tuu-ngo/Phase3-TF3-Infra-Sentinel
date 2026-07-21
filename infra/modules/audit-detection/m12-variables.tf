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
