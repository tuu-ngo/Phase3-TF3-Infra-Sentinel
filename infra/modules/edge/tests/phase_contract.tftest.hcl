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
    private_subnet_ids          = ["subnet-a", "subnet-b", "subnet-c"]
    private_alb_name            = "techx-tf3-frontend-internal"
    edge_phase                  = "invalid"
    cloudfront_staging_selector = "test-only"
  }

  expect_failures = [var.edge_phase]
}
