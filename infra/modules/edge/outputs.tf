output "cloudfront_domain_name" {
  value = "https://${aws_cloudfront_distribution.frontend.domain_name}"
}
