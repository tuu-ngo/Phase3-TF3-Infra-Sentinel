locals {
  waf_enabled               = contains(["waf", "staging", "private", "rollback"], var.edge_phase)
  private_origin_enabled    = contains(["staging", "private", "rollback"], var.edge_phase)
  staging_resources_enabled = contains(["staging", "private", "rollback"], var.edge_phase)
  staging_traffic_enabled   = var.edge_phase == "staging"
  primary_uses_private      = var.edge_phase == "private"

  public_origin_id  = "frontend-proxy-alb"
  private_origin_id = "frontend-private-alb"

  operations_path_prefixes = [
    "/grafana",
    "/jaeger",
    "/loadgen",
    "/feature",
  ]
}

data "aws_cloudfront_cache_policy" "caching_disabled" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_origin_request_policy" "all_viewer_except_host" {
  name = "Managed-AllViewerExceptHostHeader"
}

data "aws_ec2_managed_prefix_list" "cloudfront_origin_facing" {
  count = local.waf_enabled ? 1 : 0

  name = "com.amazonaws.global.cloudfront.origin-facing"
}

data "aws_lb" "private_frontend" {
  count = local.private_origin_enabled ? 1 : 0

  name = var.private_alb_name
}

resource "aws_security_group" "internal_alb" {
  count = local.waf_enabled ? 1 : 0

  name        = "${var.cluster_name}-internal-alb"
  description = "Allow CloudFront VPC origin traffic to the internal frontend ALB"
  vpc_id      = var.vpc_id

  ingress {
    description     = "HTTP from CloudFront origin-facing addresses"
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    prefix_list_ids = [data.aws_ec2_managed_prefix_list.cloudfront_origin_facing[0].id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.cluster_name}-internal-alb"
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_wafv2_web_acl" "frontend" {
  count    = local.waf_enabled ? 1 : 0
  provider = aws.us_east_1

  name        = "${var.cluster_name}-cloudfront"
  description = "Protect the storefront edge and block operations-only routes"
  scope       = "CLOUDFRONT"

  default_action {
    allow {}
  }

  rule {
    name     = "block-operations-paths"
    priority = 10

    action {
      block {}
    }

    statement {
      or_statement {
        dynamic "statement" {
          for_each = toset(local.operations_path_prefixes)

          content {
            byte_match_statement {
              positional_constraint = "STARTS_WITH"
              search_string         = statement.value

              field_to_match {
                uri_path {}
              }

              text_transformation {
                priority = 0
                type     = "LOWERCASE"
              }
            }
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.cluster_name}-block-operations-paths"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.cluster_name}-cloudfront"
    sampled_requests_enabled   = true
  }
}

resource "aws_cloudfront_vpc_origin" "frontend" {
  count = local.private_origin_enabled ? 1 : 0

  vpc_origin_endpoint_config {
    name                   = var.private_alb_name
    arn                    = data.aws_lb.private_frontend[0].arn
    http_port              = 80
    https_port             = 443
    origin_protocol_policy = "http-only"

    origin_ssl_protocols {
      items    = ["TLSv1.2"]
      quantity = 1
    }
  }

  tags = {
    Name = "${var.cluster_name}-frontend"
  }
}

resource "aws_cloudfront_distribution" "staging" {
  count = local.staging_resources_enabled ? 1 : 0

  enabled     = true
  staging     = true
  comment     = "${var.cluster_name} - private origin staging"
  price_class = "PriceClass_All"
  web_acl_id  = aws_wafv2_web_acl.frontend[0].arn

  origin {
    domain_name = data.aws_lb.private_frontend[0].dns_name
    origin_id   = local.private_origin_id

    vpc_origin_config {
      vpc_origin_id = aws_cloudfront_vpc_origin.frontend[0].id
    }
  }

  default_cache_behavior {
    target_origin_id       = local.private_origin_id
    viewer_protocol_policy = "redirect-to-https"

    allowed_methods = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods  = ["GET", "HEAD"]

    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer_except_host.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

resource "aws_cloudfront_continuous_deployment_policy" "frontend" {
  count = local.staging_resources_enabled ? 1 : 0

  enabled = local.staging_traffic_enabled

  staging_distribution_dns_names {
    items    = [aws_cloudfront_distribution.staging[0].domain_name]
    quantity = 1
  }

  traffic_config {
    type = "SingleHeader"

    single_header_config {
      header = "aws-cf-cd-techx-private-origin"
      value  = var.cloudfront_staging_selector
    }
  }

  lifecycle {
    precondition {
      condition     = !local.staging_resources_enabled || length(trimspace(var.cloudfront_staging_selector)) > 0
      error_message = "cloudfront_staging_selector must be set while staging resources are retained."
    }
  }
}

resource "aws_cloudfront_distribution" "frontend" {
  enabled                         = true
  comment                         = "${var.cluster_name} - frontend-proxy"
  price_class                     = "PriceClass_All"
  web_acl_id                      = local.waf_enabled ? aws_wafv2_web_acl.frontend[0].arn : null
  continuous_deployment_policy_id = local.staging_resources_enabled ? aws_cloudfront_continuous_deployment_policy.frontend[0].id : ""

  origin {
    domain_name = local.primary_uses_private ? data.aws_lb.private_frontend[0].dns_name : var.frontend_alb_dns_name
    origin_id   = local.primary_uses_private ? local.private_origin_id : local.public_origin_id

    dynamic "custom_origin_config" {
      for_each = local.primary_uses_private ? [] : [1]

      content {
        http_port              = 80
        https_port             = 443
        origin_protocol_policy = "http-only"
        origin_ssl_protocols   = ["TLSv1.2"]
      }
    }

    dynamic "vpc_origin_config" {
      for_each = local.primary_uses_private ? [1] : []

      content {
        vpc_origin_id = aws_cloudfront_vpc_origin.frontend[0].id
      }
    }
  }

  default_cache_behavior {
    target_origin_id       = local.primary_uses_private ? local.private_origin_id : local.public_origin_id
    viewer_protocol_policy = "redirect-to-https"

    allowed_methods = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods  = ["GET", "HEAD"]

    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer_except_host.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}
