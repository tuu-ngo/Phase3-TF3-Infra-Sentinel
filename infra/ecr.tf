locals {
  techx_ecr_repository_name = "techx-corp"

  # Image tags are produced by CI in the form "<gitsha>-<service>", so matching by
  # service requires tagPatternList (e.g. "*-checkout"), not tagPrefixList.
  techx_ecr_services = [
    "accounting",
    "ad",
    "cart",
    "checkout",
    "currency",
    "email",
    "flagd-ui",
    "fraud-detection",
    "frontend",
    "frontend-proxy",
    "image-provider",
    "kafka",
    "llm",
    "load-generator",
    "payment",
    "product-catalog",
    "product-reviews",
    "quote",
    "recommendation",
    "shipping",
  ]

  techx_ecr_lifecycle_rules = concat(
    [
      for idx, service in local.techx_ecr_services : {
        rulePriority = idx + 1
        description  = "Keep the 10 newest tagged builds for ${service}"
        selection = {
          tagStatus      = "tagged"
          tagPatternList = ["*-${service}"]
          countType      = "imageCountMoreThan"
          countNumber    = 10
        }
        action = {
          type = "expire"
        }
      }
    ],
    [
      {
        rulePriority = length(local.techx_ecr_services) + 1
        description  = "Expire untagged build artifacts older than 7 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = {
          type = "expire"
        }
      }
    ]
  )
}

resource "aws_ecr_lifecycle_policy" "techx_corp" {
  repository = local.techx_ecr_repository_name

  policy = jsonencode({
    rules = local.techx_ecr_lifecycle_rules
  })
}
