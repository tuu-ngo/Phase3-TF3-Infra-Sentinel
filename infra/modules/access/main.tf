data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  # STANDARD AL2023 only — NOT "minimal". The minimal image ships without
  # amazon-ssm-agent, so a bastion built from it never registers with SSM and the
  # private-EKS-API tunnel is dead on arrival. The old glob `al2023-ami-*-x86_64`
  # also matched `al2023-ami-minimal-*` and most_recent picked minimal — this was
  # the root cause of the bastion-never-online incident on the new account (13/07,
  # ~30m lost). `al2023-ami-2023.*` excludes minimal (its name is
  # `al2023-ami-minimal-2023.*`, which does not match this pattern).
  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }
}

resource "aws_security_group" "bastion" {
  name        = "${var.cluster_name}-bastion-sg"
  description = "SSM bastion for EKS private API access - no inbound rule needed"
  vpc_id      = var.vpc_id

  egress {
    description = "HTTPS to private VPC endpoints and the private EKS API"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    description = "UDP DNS to the Amazon-provided VPC resolver"
    from_port   = 53
    to_port     = 53
    protocol    = "udp"
    cidr_blocks = ["${cidrhost(var.vpc_cidr, 2)}/32"]
  }

  egress {
    description = "TCP DNS fallback to the Amazon-provided VPC resolver"
    from_port   = 53
    to_port     = 53
    protocol    = "tcp"
    cidr_blocks = ["${cidrhost(var.vpc_cidr, 2)}/32"]
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
  subnet_id                   = var.private_subnet_ids[0]
  vpc_security_group_ids      = [aws_security_group.bastion.id]
  iam_instance_profile        = aws_iam_instance_profile.bastion.name
  associate_public_ip_address = false

  metadata_options {
    http_tokens = "required"
  }

  root_block_device {
    encrypted = true
  }

  tags = {
    Name = "${var.cluster_name}-bastion"
  }

  lifecycle {
    ignore_changes = [ami]
  }
}

resource "aws_security_group_rule" "cluster_from_bastion" {
  type                     = "ingress"
  from_port                = 443
  to_port                  = 443
  protocol                 = "tcp"
  security_group_id        = var.cluster_security_group_id
  source_security_group_id = aws_security_group.bastion.id
  description              = "Allow SSM bastion to reach EKS API"
}
