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
    1. Deploy the main stack from your laptop once:
       terraform -chdir=infra/main init -backend-config="bucket=${aws_s3_bucket.state.bucket}" -backend-config="region=${var.region}"
       terraform -chdir=infra/main apply

    2. Then add these GitHub repository variables (Settings > Secrets and variables > Actions > Variables):
       AWS_REGION          = ${var.region}
       AWS_DEPLOY_ROLE_ARN = ${aws_iam_role.github_deploy.arn}
       TF_STATE_BUCKET     = ${aws_s3_bucket.state.bucket}
  EOT
}
