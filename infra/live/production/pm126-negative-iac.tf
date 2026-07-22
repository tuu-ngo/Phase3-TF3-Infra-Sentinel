# PM-126 NEGATIVE CI FIXTURE — DO NOT MERGE.
# Expected finding: AVD-AWS-0104 (CRITICAL), unrestricted security-group egress.
resource "aws_security_group" "pm126_negative_ci_fixture" {
  name        = "pm126-negative-ci-fixture"
  description = "Disposable PM-126 negative CI fixture; this PR must never be merged"
  vpc_id      = module.network.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
