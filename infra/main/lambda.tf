# Code plus config. Nothing else to bundle: stdlib only, and boto3 ships with the runtime.
data "archive_file" "lambda" {
  type        = "zip"
  output_path = "${path.module}/.build/lambda.zip"

  dynamic "source" {
    for_each = fileset("${local.repo_root}/src", "jobradar/**/*.py")

    content {
      content  = file("${local.repo_root}/src/${source.value}")
      filename = source.value
    }
  }

  source {
    content  = file("${local.repo_root}/config/job-radar.toml")
    filename = "job-radar.toml"
  }
}

resource "aws_cloudwatch_log_group" "lambda" {
  #checkov:skip=CKV_AWS_158:Logs hold no secrets; a customer-managed KMS key costs $1 a month
  #checkov:skip=CKV_AWS_338:Two weeks of logs is enough to debug a twice-daily job and keeps storage free

  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_days
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name                 = "${var.name}-lambda"
  assume_role_policy   = data.aws_iam_policy_document.lambda_assume.json
  permissions_boundary = local.permissions_boundary
}

data "aws_iam_policy_document" "lambda" {
  #checkov:skip=CKV_AWS_356:kms:Decrypt needs "*"; it is limited to calls made through SSM

  statement {
    sid       = "WriteLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.lambda.arn}:*"]
  }

  statement {
    sid = "SeenJobsTable"
    actions = [
      "dynamodb:BatchGetItem",
      "dynamodb:BatchWriteItem",
      "dynamodb:GetItem",
      "dynamodb:PutItem",
    ]
    resources = [aws_dynamodb_table.seen.arn]
  }

  statement {
    sid       = "ReadTelegramSettings"
    actions   = ["ssm:GetParameter"]
    resources = [aws_ssm_parameter.telegram_token.arn, aws_ssm_parameter.telegram_chat_id.arn]
  }

  statement {
    sid       = "DecryptSettingsThroughSsm"
    actions   = ["kms:Decrypt"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${var.region}.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${var.name}-lambda"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}

resource "aws_lambda_function" "radar" {
  #checkov:skip=CKV_AWS_50:X-Ray tracing adds little for one short function
  #checkov:skip=CKV_AWS_115:New accounts cannot reserve concurrency (the minimum of 10 unreserved), and runs never overlap
  #checkov:skip=CKV_AWS_116:Failures raise the CloudWatch alarm, and the next scheduled run retries the same jobs
  #checkov:skip=CKV_AWS_117:The function only calls public APIs; a VPC would need a NAT gateway (about $32 a month)
  #checkov:skip=CKV_AWS_173:Environment variables hold parameter names only, not secrets
  #checkov:skip=CKV_AWS_272:Code signing is not needed for a single-maintainer project

  function_name    = local.function_name
  description      = "Sends new DevOps job ads to Telegram"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.13"
  architectures    = ["arm64"]
  handler          = "jobradar.handler.lambda_handler"
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  memory_size      = var.lambda_memory_mb
  timeout          = var.lambda_timeout_seconds

  environment {
    variables = {
      SEEN_TABLE             = aws_dynamodb_table.seen.name
      TELEGRAM_TOKEN_PARAM   = aws_ssm_parameter.telegram_token.name
      TELEGRAM_CHAT_ID_PARAM = aws_ssm_parameter.telegram_chat_id.name
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda, aws_iam_role_policy.lambda]
}
