data "aws_caller_identity" "current" {}

locals {
  account_id    = data.aws_caller_identity.current.account_id
  function_name = var.name
  repo_root     = "${path.module}/../.."

  permissions_boundary = (
    var.use_permissions_boundary
    ? "arn:aws:iam::${local.account_id}:policy/${var.name}-workload-boundary"
    : null
  )
}

# Created with a placeholder; the real values are set with the AWS CLI so they stay out of state.
resource "aws_ssm_parameter" "telegram_token" {
  #checkov:skip=CKV_AWS_337:SecureString with the AWS managed key; a customer-managed key costs $1 a month

  name        = "/${var.name}/telegram/bot-token"
  description = "Telegram bot token for ${var.name}"
  type        = "SecureString"
  value       = "set-me-with-the-aws-cli"

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "telegram_chat_id" {
  #checkov:skip=CKV_AWS_337:SecureString with the AWS managed key; a customer-managed key costs $1 a month

  name        = "/${var.name}/telegram/chat-id"
  description = "Telegram chat that receives the ${var.name} digest"
  type        = "SecureString"
  value       = "set-me-with-the-aws-cli"

  lifecycle {
    ignore_changes = [value]
  }
}

# Jobs already sent. 5/5 capacity is inside the always-free 25/25; the TTL clears old items.
resource "aws_dynamodb_table" "seen" {
  #checkov:skip=CKV_AWS_28:Point-in-time recovery is paid; losing this table only means a few repeat alerts
  #checkov:skip=CKV_AWS_119:Encrypted at rest with the AWS owned key; a customer-managed key costs $1 a month
  #checkov:skip=CKV2_AWS_16:Auto scaling is unnecessary for a few hundred writes a month

  name           = "${var.name}-seen-jobs"
  billing_mode   = "PROVISIONED"
  read_capacity  = 5
  write_capacity = 5
  hash_key       = "job_key"

  attribute {
    name = "job_key"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}
