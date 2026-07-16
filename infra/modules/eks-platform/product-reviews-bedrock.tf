locals {
  product_reviews_namespace       = "techx-tf3"
  product_reviews_service_account = "product-reviews-bedrock"
  bedrock_region                  = "us-east-1"
  bedrock_summary_model_id        = "amazon.nova-lite-v1:0"
  bedrock_judge_model_id          = "amazon.nova-micro-v1:0"
}

data "aws_iam_policy_document" "product_reviews_bedrock_assume_role" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [module.eks.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${module.eks.oidc_provider}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "${module.eks.oidc_provider}:sub"
      values   = ["system:serviceaccount:${local.product_reviews_namespace}:${local.product_reviews_service_account}"]
    }
  }
}

resource "aws_iam_role" "product_reviews_bedrock" {
  name               = "${var.cluster_name}-product-reviews-bedrock"
  assume_role_policy = data.aws_iam_policy_document.product_reviews_bedrock_assume_role.json
}

resource "aws_iam_role_policy" "product_reviews_bedrock" {
  name = "${var.cluster_name}-product-reviews-bedrock"
  role = aws_iam_role.product_reviews_bedrock.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "InvokeApprovedBedrockModels"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
        ]
        Resource = [
          "arn:aws:bedrock:${local.bedrock_region}::foundation-model/${local.bedrock_summary_model_id}",
          "arn:aws:bedrock:${local.bedrock_region}::foundation-model/${local.bedrock_judge_model_id}",
        ]
      },
    ]
  })
}
