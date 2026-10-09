variable "region" {
  description = "AWS region. Keep it the same as the bootstrap stack."
  type        = string
  default     = "eu-west-1"
}

variable "name" {
  description = "Name prefix for every resource. Must match the bootstrap stack."
  type        = string
  default     = "job-radar"
}

variable "schedule_expression" {
  description = "When to run, as an EventBridge Scheduler expression."
  type        = string
  default     = "cron(0 8,18 * * ? *)"
}

variable "schedule_timezone" {
  description = "Time zone for the schedule."
  type        = string
  default     = "Africa/Lagos"
}

variable "alert_email" {
  description = "Email that gets an alert if a run fails. Leave empty for no email."
  type        = string
  default     = ""
}

variable "log_retention_days" {
  description = "How long to keep Lambda logs."
  type        = number
  default     = 14
}

variable "lambda_memory_mb" {
  description = "Lambda memory in MB. 256 MB is plenty for a few thousand job ads."
  type        = number
  default     = 256
}

variable "lambda_timeout_seconds" {
  description = "Lambda timeout in seconds. Runs take seconds; this covers several slow boards."
  type        = number
  default     = 300
}

variable "use_permissions_boundary" {
  description = "Attach the bootstrap stack's permissions boundary to the roles. Required for GitHub deploys."
  type        = bool
  default     = true
}
