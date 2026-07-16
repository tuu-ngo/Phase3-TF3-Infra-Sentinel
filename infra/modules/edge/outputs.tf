output "cloudfront_domain_name" {
  value = "https://${aws_cloudfront_distribution.frontend.domain_name}"
}

output "cloudfront_distribution_id" {
  value = aws_cloudfront_distribution.frontend.id
}

output "internal_alb_security_group_id" {
  value = try(aws_security_group.internal_alb[0].id, null)
}

output "cloudfront_vpc_origin_id" {
  value = try(aws_cloudfront_vpc_origin.frontend[0].id, null)
}
