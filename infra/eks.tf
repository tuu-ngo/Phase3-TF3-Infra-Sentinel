# Cluster secrets (etcd envelope) encryption key - created directly here
# instead of letting the eks module create its own (module.eks's built-in
# KMS submodule is fetched via `git::`, which this environment can't reach;
# a plain aws_kms_key avoids that dependency entirely and does the same job).
resource "aws_kms_key" "eks" {
  description             = "EKS cluster secrets encryption - ${var.cluster_name}"
  deletion_window_in_days = 7
  enable_key_rotation     = true
}

resource "aws_kms_alias" "eks" {
  name          = "alias/${var.cluster_name}-eks"
  target_key_id = aws_kms_key.eks.key_id
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.31"

  cluster_name    = var.cluster_name
  cluster_version = var.cluster_version

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  # Private-only API access as of 09/07 - team members reach it through the
  # SSM bastion (bastion.tf) instead of an IP allowlist. This is what fixes
  # the repeated "someone's terraform apply overwrote the CIDR list and
  # locked everyone out" incidents documented in CLAUDE.md - there's no CIDR
  # list to drift anymore.
  cluster_endpoint_public_access  = false
  cluster_endpoint_private_access = true

  create_kms_key = false
  cluster_encryption_config = {
    resources        = ["secrets"]
    provider_key_arn = aws_kms_key.eks.arn
  }

  enable_irsa = true

  eks_managed_node_group_defaults = {
    ami_type = "AL2023_x86_64_STANDARD"
  }

  eks_managed_node_groups = {
    default = {
      instance_types = [var.node_instance_type]
      capacity_type  = "ON_DEMAND" # not spot yet - baseline is still single-replica per service (see CLAUDE.md); revisit once replicas/PDB are in place

      min_size     = var.node_min_size
      max_size     = var.node_max_size
      desired_size = var.node_desired_size

      # Worker nodes always private - no direct route to the internet except via NAT.
      subnet_ids = module.vpc.private_subnets
    }
  }

  # TF3 members who need kubectl/helm access - fill in real ARNs in terraform.tfvars.
  access_entries = {
    for arn in var.eks_admin_principal_arns : arn => {
      principal_arn = arn
      policy_associations = {
        admin = {
          policy_arn = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
          access_scope = {
            type = "cluster"
          }
        }
      }
    }
  }
}
