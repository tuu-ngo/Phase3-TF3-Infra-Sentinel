mock_provider "aws" {}

mock_provider "aws" {
  alias = "us_east_1"
}

run "rejects_unknown_phase" {
  command = plan

  variables {
    cluster_name                = "techx-corp-tf3"
    frontend_alb_dns_name       = "public.example.elb.amazonaws.com"
    vpc_id                      = "vpc-00000000000000000"
    private_alb_name            = "techx-tf3-frontend-internal"
    edge_phase                  = "invalid"
    cloudfront_staging_selector = "test-only"
  }

  expect_failures = [var.edge_phase]
}

run "public_phase_preserves_public_origin" {
  command = plan

  variables {
    cluster_name                = "techx-corp-tf3"
    frontend_alb_dns_name       = "public.example.elb.amazonaws.com"
    vpc_id                      = "vpc-00000000000000000"
    private_alb_name            = "techx-tf3-frontend-internal"
    edge_phase                  = "public"
    cloudfront_staging_selector = ""
  }

  assert {
    condition     = length(aws_wafv2_web_acl.frontend) == 0
    error_message = "Public phase must not create or associate WAF."
  }

  assert {
    condition     = one(aws_cloudfront_distribution.frontend.origin).domain_name == "public.example.elb.amazonaws.com"
    error_message = "Public phase must preserve the existing public ALB origin."
  }
}

run "waf_phase_adds_guard_without_origin_cutover" {
  command = plan

  variables {
    cluster_name                = "techx-corp-tf3"
    frontend_alb_dns_name       = "public.example.elb.amazonaws.com"
    vpc_id                      = "vpc-00000000000000000"
    private_alb_name            = "techx-tf3-frontend-internal"
    edge_phase                  = "waf"
    cloudfront_staging_selector = ""
  }

  assert {
    condition     = length(aws_wafv2_web_acl.frontend) == 1
    error_message = "WAF phase must create one WebACL."
  }

  assert {
    condition     = length(aws_security_group.internal_alb) == 1
    error_message = "WAF phase must create the private ALB security boundary."
  }

  assert {
    condition = alltrue([
      for transformation in one(one(one(aws_wafv2_web_acl.frontend).rule).statement).or_statement[0].statement[0].byte_match_statement[0].text_transformation :
      contains(["URL_DECODE", "NORMALIZE_PATH", "LOWERCASE"], transformation.type)
    ]) && length(one(one(one(aws_wafv2_web_acl.frontend).rule).statement).or_statement[0].statement[0].byte_match_statement[0].text_transformation) == 3
    error_message = "Operations path matching must decode, normalize, and lowercase URI paths."
  }

  assert {
    condition     = one(aws_cloudfront_distribution.frontend.origin).domain_name == "public.example.elb.amazonaws.com"
    error_message = "WAF phase must keep the existing public ALB origin."
  }
}

run "staging_phase_keeps_primary_on_public_origin" {
  command = plan

  override_data {
    target = data.aws_lb.private_frontend[0]
    values = {
      arn      = "arn:aws:elasticloadbalancing:ap-southeast-1:197826770971:loadbalancer/app/techx-tf3-frontend-internal/0123456789abcdef"
      dns_name = "internal.example.elb.amazonaws.com"
    }
  }

  variables {
    cluster_name                = "techx-corp-tf3"
    frontend_alb_dns_name       = "public.example.elb.amazonaws.com"
    vpc_id                      = "vpc-00000000000000000"
    private_alb_name            = "techx-tf3-frontend-internal"
    edge_phase                  = "staging"
    cloudfront_staging_selector = "test-only"
  }

  assert {
    condition     = length(aws_cloudfront_vpc_origin.frontend) == 1
    error_message = "Staging phase must create one VPC Origin."
  }

  assert {
    condition     = length(aws_cloudfront_distribution.staging) == 1
    error_message = "Staging phase must create one staging distribution."
  }

  assert {
    condition     = one(aws_cloudfront_distribution.frontend.origin).domain_name == "public.example.elb.amazonaws.com"
    error_message = "Staging phase must keep normal traffic on the public origin."
  }
}

run "private_phase_cuts_primary_to_vpc_origin" {
  command = plan

  override_data {
    target = data.aws_lb.private_frontend[0]
    values = {
      arn      = "arn:aws:elasticloadbalancing:ap-southeast-1:197826770971:loadbalancer/app/techx-tf3-frontend-internal/0123456789abcdef"
      dns_name = "internal.example.elb.amazonaws.com"
    }
  }

  variables {
    cluster_name                = "techx-corp-tf3"
    frontend_alb_dns_name       = "public.example.elb.amazonaws.com"
    vpc_id                      = "vpc-00000000000000000"
    private_alb_name            = "techx-tf3-frontend-internal"
    edge_phase                  = "private"
    cloudfront_staging_selector = "test-only"
  }

  assert {
    condition     = length(aws_cloudfront_distribution.staging) == 1
    error_message = "Private phase must retain staging resources until controlled cleanup."
  }

  assert {
    condition     = length(aws_cloudfront_vpc_origin.frontend) == 1
    error_message = "Private phase must retain the VPC Origin."
  }

  assert {
    condition     = length(one(aws_cloudfront_distribution.frontend.origin).vpc_origin_config) == 1
    error_message = "Private phase must use VPC Origin for primary traffic."
  }

  assert {
    condition     = aws_cloudfront_continuous_deployment_policy.frontend[0].enabled == false
    error_message = "Private phase must disable staging traffic before cutover."
  }
}

run "rollback_phase_restores_public_and_retains_vpc_origin" {
  command = plan

  override_data {
    target = data.aws_lb.private_frontend[0]
    values = {
      arn      = "arn:aws:elasticloadbalancing:ap-southeast-1:197826770971:loadbalancer/app/techx-tf3-frontend-internal/0123456789abcdef"
      dns_name = "internal.example.elb.amazonaws.com"
    }
  }

  variables {
    cluster_name                = "techx-corp-tf3"
    frontend_alb_dns_name       = "public.example.elb.amazonaws.com"
    vpc_id                      = "vpc-00000000000000000"
    private_alb_name            = "techx-tf3-frontend-internal"
    edge_phase                  = "rollback"
    cloudfront_staging_selector = "test-only"
  }

  assert {
    condition     = length(aws_cloudfront_vpc_origin.frontend) == 1
    error_message = "Rollback must retain the VPC Origin for investigation."
  }

  assert {
    condition     = length(aws_cloudfront_distribution.staging) == 1
    error_message = "Rollback must retain staging resources until controlled cleanup."
  }

  assert {
    condition     = one(aws_cloudfront_distribution.frontend.origin).domain_name == "public.example.elb.amazonaws.com"
    error_message = "Rollback must restore the public ALB as primary origin."
  }

  assert {
    condition     = aws_cloudfront_continuous_deployment_policy.frontend[0].enabled == false
    error_message = "Rollback must keep staging traffic disabled."
  }
}
