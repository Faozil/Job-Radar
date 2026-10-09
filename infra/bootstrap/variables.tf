variable "region" {
  description = "AWS region for every job-radar resource."
  type        = string
  default     = "eu-west-1"
}

variable "name" {
  description = "Name prefix. The deploy role can only manage resources whose names start with it."
  type        = string
  default     = "job-radar"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,20}$", var.name))
    error_message = "Use 3-21 lowercase letters, digits or hyphens, starting with a letter."
  }
}

variable "github_repository" {
  description = "GitHub repository allowed to deploy, as owner/name, with the exact case GitHub shows."
  type        = string
  default     = "Faozil/Job-Radar"

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "Use the owner/name form, for example Faozil/Job-Radar."
  }
}

variable "github_environment" {
  description = "GitHub Actions environment the deploy job runs in. Only that environment can assume the role."
  type        = string
  default     = "production"
}

variable "create_github_oidc_provider" {
  description = "Set to false if the account already has the GitHub OIDC provider (one per account)."
  type        = bool
  default     = true
}
