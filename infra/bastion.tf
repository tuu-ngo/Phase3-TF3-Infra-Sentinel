# SSM bastion - lets TF3 members reach the (now-private-only) EKS API without
# ever needing their own IP allowlisted. No SSH key, no public IP, no inbound
# security group rule at all: SSM Session Manager tunnels over an
# outbound-initiated HTTPS connection from the agent on this instance to the
# AWS SSM service, authenticated purely by IAM - not by network source.

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  # MUST be the STANDARD AL2023, not "minimal" — the minimal image ships WITHOUT
  # amazon-ssm-agent, so a bastion built from it never registers with SSM and the
  # tunnel is dead on arrival. The old glob `al2023-ami-*-x86_64` also matched
  # `al2023-ami-minimal-*` and most_recent picked minimal (root cause of the
  # bastion-never-online incident on the new account, 13/07). This pattern excludes
  # minimal because its name is `al2023-ami-minimal-2023.*`, not `al2023-ami-2023.*`.
  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }
}

resource "aws_security_group" "bastion" {
  name        = "${var.cluster_name}-bastion-sg"
  description = "SSM bastion for EKS private API access - no inbound rule needed"
  vpc_id      = module.vpc.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.cluster_name}-bastion-sg"
  }
}

resource "aws_iam_role" "bastion" {
  name = "${var.cluster_name}-bastion-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "bastion_ssm" {
  role       = aws_iam_role.bastion.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "bastion" {
  name = "${var.cluster_name}-bastion-profile"
  role = aws_iam_role.bastion.name
}

resource "aws_instance" "bastion" {
  ami                         = data.aws_ami.al2023.id
  instance_type               = "t3.micro"
  subnet_id                   = module.vpc.private_subnets[0]
  vpc_security_group_ids      = [aws_security_group.bastion.id]
  iam_instance_profile        = aws_iam_instance_profile.bastion.name
  associate_public_ip_address = false

  metadata_options {
    http_tokens = "required" # IMDSv2 only
  }

  tags = {
    Name = "${var.cluster_name}-bastion"
  }

  # `data.aws_ami.al2023` uses most_recent=true, so a newly published AL2023 AMI
  # changes the resolved AMI id, and a changed `ami` forces instance REPLACEMENT.
  # On 12/07 this latent replacement rode along with an unrelated apply and, because
  # the AWS account was concurrently on hold (RunInstances blocked), the bastion was
  # destroyed and could not be recreated - locking everyone out of the private EKS API.
  # Ignore ami drift so the bastion is only ever replaced when we deliberately change it.
  # (See docs/postmortem/0002-* for the full incident.)
  lifecycle {
    ignore_changes = [ami]
  }
}

# Let the bastion reach the EKS control plane (needed now that the API is
# private-only - see cluster_endpoint_public_access = false in eks.tf).
resource "aws_security_group_rule" "cluster_from_bastion" {
  type                     = "ingress"
  from_port                = 443
  to_port                  = 443
  protocol                 = "tcp"
  security_group_id        = module.eks.cluster_security_group_id
  source_security_group_id = aws_security_group.bastion.id
  description              = "Allow SSM bastion to reach EKS API"
}
