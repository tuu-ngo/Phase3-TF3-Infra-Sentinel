# CloudFront in front of the frontend-proxy ALB.
#
# Why: gives a stable *.cloudfront.net hostname with HTTPS out of the box
# (CloudFront's default certificate covers it - no ACM cert / owned domain
# needed). Once the team has a real domain, point a CNAME/ALIAS at this
# distribution's domain_name and add a custom viewer certificate - the ALB
# and Ingress underneath don't need to change.
#
# ALB stays HTTP-only (origin_protocol_policy = "http-only"); CloudFront
# terminates TLS at the edge for viewers. Traffic between CloudFront and the
# ALB travels over the AWS backbone, not the public internet.

data "aws_cloudfront_cache_policy" "caching_disabled" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_origin_request_policy" "all_viewer_except_host" {
  name = "Managed-AllViewerExceptHostHeader"
}

resource "aws_cloudfront_distribution" "frontend" {
  enabled     = true
  comment     = "${var.cluster_name} - frontend-proxy"
  price_class = "PriceClass_All"

  origin {
    domain_name = var.frontend_alb_dns_name
    origin_id   = "frontend-proxy-alb"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id       = "frontend-proxy-alb"
    viewer_protocol_policy = "redirect-to-https"

    allowed_methods = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods  = ["GET", "HEAD"]

    # Dynamic storefront app, not a static site - don't cache at the edge.
    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer_except_host.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # Free default *.cloudfront.net cert. Swap to a custom ACM cert
  # (us-east-1 required for CloudFront) once a real domain is attached.
  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

output "cloudfront_domain_name" {
  description = "Public HTTPS address for the storefront"
  value       = "https://${aws_cloudfront_distribution.frontend.domain_name}"
}
