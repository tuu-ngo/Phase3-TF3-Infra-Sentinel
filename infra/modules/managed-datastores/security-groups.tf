# ── Security Groups ──────────────────────────────────────────────────────────
# All datastores are private — no inbound from the internet.
# Only EKS node SG (and the VPC CIDR for MSK IAM/TLS bootstrap) can connect.

# ── RDS PostgreSQL ────────────────────────────────────────────────────────────

resource "aws_security_group" "rds" {
  name        = "${var.cluster_name}-rds-sg"
  description = "Allow PostgreSQL TLS traffic from EKS nodes only"
  vpc_id      = var.vpc_id

  ingress {
    description     = "PostgreSQL from EKS nodes"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.eks_node_security_group_id]
  }

  egress {
    description = "Allow all outbound (RDS needs to reach KMS endpoints etc.)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.cluster_name}-rds-sg"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# ── ElastiCache Redis ─────────────────────────────────────────────────────────

resource "aws_security_group" "elasticache" {
  name        = "${var.cluster_name}-elasticache-sg"
  description = "Allow Redis TLS traffic from EKS nodes only"
  vpc_id      = var.vpc_id

  ingress {
    description     = "Redis TLS from EKS nodes"
    from_port       = 6380
    to_port         = 6380
    protocol        = "tcp"
    security_groups = [var.eks_node_security_group_id]
  }

  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.cluster_name}-elasticache-sg"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# ── MSK Kafka ─────────────────────────────────────────────────────────────────

resource "aws_security_group" "msk" {
  name        = "${var.cluster_name}-msk-sg"
  description = "Allow Kafka TLS/SASL traffic from EKS nodes only"
  vpc_id      = var.vpc_id

  # TLS (9094) — encrypted transport for SASL/SCRAM clients
  ingress {
    description     = "Kafka TLS from EKS nodes"
    from_port       = 9094
    to_port         = 9094
    protocol        = "tcp"
    security_groups = [var.eks_node_security_group_id]
  }

  # IAM auth over TLS (9098) — for workloads using IAM authentication
  ingress {
    description     = "Kafka IAM/TLS from EKS nodes"
    from_port       = 9098
    to_port         = 9098
    protocol        = "tcp"
    security_groups = [var.eks_node_security_group_id]
  }

  # Inter-broker (within the SG itself — required for MSK broker-to-broker TLS)
  ingress {
    description = "MSK inter-broker TLS"
    from_port   = 9094
    to_port     = 9094
    protocol    = "tcp"
    self        = true
  }

  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.cluster_name}-msk-sg"
  }

  lifecycle {
    create_before_destroy = true
  }
}
