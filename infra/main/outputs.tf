output "function_name" {
  value = aws_lambda_function.radar.function_name
}

output "seen_jobs_table" {
  value = aws_dynamodb_table.seen.name
}

output "schedule" {
  value = "${var.schedule_expression} in ${var.schedule_timezone}"
}

output "email_address_parameter" {
  value = aws_ssm_parameter.email_address.name
}

output "email_password_parameter" {
  value = aws_ssm_parameter.email_password.name
}

output "test_command" {
  description = "Run the radar once, right now."
  value       = "aws lambda invoke --region ${var.region} --function-name ${aws_lambda_function.radar.function_name} --cli-binary-format raw-in-base64-out --payload '{}' /dev/stdout"
}
