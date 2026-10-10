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

variable "email_address" {
  description = "Gmail address that sends and receives the digest (GitHub secret EMAIL_ADDRESS)."
  type        = string
  ephemeral   = true
  sensitive   = true

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+$", var.email_address))
    error_message = "Add the EMAIL_ADDRESS secret (your Gmail address) to the production environment."
  }
}

variable "email_app_password" {
  description = "Gmail app password (GitHub secret EMAIL_APP_PASSWORD)."
  type        = string
  ephemeral   = true
  sensitive   = true

  validation {
    condition     = length(trimspace(var.email_app_password)) > 0
    error_message = "Add the EMAIL_APP_PASSWORD secret to the production environment."
  }
}

variable "email_settings_version" {
  description = "Increase by one after changing the email secrets, so the next deploy writes them to SSM."
  type        = number
  default     = 1
}

variable "alert_email" {
  description = "Email that gets an alert if a run fails (GitHub secret ALERT_EMAIL). Empty for none."
  type        = string
  default     = ""
}

variable "log_retention_days" {
  description = "How long to keep Lambda logs."
  type        = number
  default     = 14
}

variable "lambda_memory_mb" {
  description = "Lambda memory in MB. A run with ~10,000 job ads peaks near 200 MB; CPU scales with memory."
  type        = number
  default     = 512
}

variable "lambda_timeout_seconds" {
  description = "Lambda timeout in seconds. A run takes about a minute; this leaves room for slow boards."
  type        = number
  default     = 300
}

variable "use_permissions_boundary" {
  description = "Attach the bootstrap stack's permissions boundary to the roles. Required for GitHub deploys."
  type        = bool
  default     = true
}
