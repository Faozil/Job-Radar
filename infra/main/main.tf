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

# The values come from GitHub secrets through ephemeral variables into write-only arguments, so
# they never land in a plan file or the state. They are written when the parameter is created and
# again only when email_settings_version changes.
resource "aws_ssm_parameter" "email_address" {
  #checkov:skip=CKV_AWS_337:SecureString with the AWS managed key; a customer-managed key costs $1 a month

  name             = "/${var.name}/email/address"
  description      = "Gmail address that sends and receives the ${var.name} digest"
  type             = "SecureString"
  value_wo         = var.email_address
  value_wo_version = var.email_settings_version
}

resource "aws_ssm_parameter" "email_password" {
  #checkov:skip=CKV_AWS_337:SecureString with the AWS managed key; a customer-managed key costs $1 a month

  name             = "/${var.name}/email/app-password"
  description      = "Gmail app password for ${var.name}"
  type             = "SecureString"
  value_wo         = var.email_app_password
  value_wo_version = var.email_settings_version
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
