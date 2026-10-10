output "state_bucket" {
  description = "S3 bucket that stores the main stack's Terraform state."
  value       = aws_s3_bucket.state.bucket
}

output "deploy_role_arn" {
  description = "IAM role GitHub Actions assumes to deploy."
  value       = aws_iam_role.github_deploy.arn
}

output "workload_boundary_arn" {
  description = "Permissions boundary the main stack attaches to its roles."
  value       = aws_iam_policy.workload_boundary.arn
}

output "next_steps" {
  description = "What to run next."
  value       = <<-EOT
    1. Back up this stack's state, under a path the deploy role cannot read:
       aws s3 cp infra/bootstrap/terraform.tfstate s3://${aws_s3_bucket.state.bucket}/bootstrap/terraform.tfstate

    2. In GitHub, add these repository variables (Settings > Secrets and variables > Actions > Variables):
       AWS_REGION          = ${var.region}
       AWS_DEPLOY_ROLE_ARN = ${aws_iam_role.github_deploy.arn}
       TF_STATE_BUCKET     = ${aws_s3_bucket.state.bucket}

    3. Create the "${var.github_environment}" environment (Settings > Environments) with the secrets
       EMAIL_ADDRESS, EMAIL_APP_PASSWORD and, optionally, ALERT_EMAIL.

    4. Run the Deploy workflow from the Actions tab. It creates everything else.
  EOT
}
