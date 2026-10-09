# Upper limit for every workload role. The deploy role can't create a role without it.
data "aws_iam_policy_document" "workload_boundary" {
  #checkov:skip=CKV_AWS_356:kms:Decrypt needs "*"; it is limited to calls made through SSM

  statement {
    sid       = "WriteLambdaLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:${var.region}:${local.account_id}:log-group:/aws/lambda/${var.name}*:*"]
  }

  statement {
    sid = "SeenJobsTable"
    actions = [
      "dynamodb:BatchGetItem",
      "dynamodb:BatchWriteItem",
      "dynamodb:GetItem",
      "dynamodb:PutItem",
    ]
    resources = ["arn:aws:dynamodb:${var.region}:${local.account_id}:table/${var.name}*"]
  }

  statement {
    sid       = "ReadSettings"
    actions   = ["ssm:GetParameter"]
    resources = ["arn:aws:ssm:${var.region}:${local.account_id}:parameter/${var.name}/*"]
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

  statement {
    sid       = "SchedulerInvokesTheFunction"
    actions   = ["lambda:InvokeFunction"]
    resources = ["arn:aws:lambda:${var.region}:${local.account_id}:function:${var.name}*"]
  }
}

resource "aws_iam_policy" "workload_boundary" {
  name        = "${var.name}-workload-boundary"
  description = "Permissions boundary for every ${var.name} workload role"
  policy      = data.aws_iam_policy_document.workload_boundary.json
}
