variable "cluster_name" {
  type = string
}

variable "deployment_label" {
  description = "Short label used in names, for example ap-southeast-1 or us-east-1."
  type        = string
}

variable "alert_email_subscriptions" {
  description = "Email recipients subscribed to the SNS topic."
  type        = list(string)
  default     = []
}

variable "event_rules" {
  description = "EventBridge rules keyed by a short rule name."
  type = map(object({
    description   = string
    sources       = list(string)
    event_sources = list(string)
    event_names   = list(string)
  }))
}

variable "allowed_automation_principal_arns" {
  description = "Automation principals that should not raise routine alerts."
  type        = list(string)
  default     = []
}

variable "human_principal_arns" {
  description = "Human principals whose secret reads should be reviewed."
  type        = list(string)
  default     = []
}

variable "secret_reader_principal_arns" {
  description = "Automation principals allowed to read watched secrets."
  type        = list(string)
  default     = []
}

variable "sensitive_secret_names" {
  description = "Secret names that should be treated as sensitive for Group 5."
  type        = list(string)
  default     = []
}

variable "suppressions" {
  description = "Time-bounded suppressions evaluated in the Lambda router."
  type = list(object({
    actor    = string
    resource = string
    start    = string
    end      = string
    reason   = string
  }))
  default = []
}

variable "include_global_service_events" {
  description = "Whether the regional trail should include global service events."
  type        = bool
  default     = false
}

variable "lambda_log_retention_days" {
  description = "Retention for Lambda execution logs."
  type        = number
  default     = 14
}

variable "trail_s3_retention_days" {
  description = "Lifecycle retention for CloudTrail objects in S3."
  type        = number
  default     = 30
}
