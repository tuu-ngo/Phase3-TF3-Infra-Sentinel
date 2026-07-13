module "network" {
  source = "../../modules/network"

  region               = var.region
  cluster_name         = var.cluster_name
  vpc_cidr             = var.vpc_cidr
  azs                  = var.azs
  private_subnet_cidrs = var.private_subnet_cidrs
  public_subnet_cidrs  = var.public_subnet_cidrs
}

module "eks_platform" {
  source = "../../modules/eks-platform"

  cluster_name             = var.cluster_name
  cluster_version          = var.cluster_version
  vpc_id                   = module.network.vpc_id
  private_subnet_ids       = module.network.private_subnet_ids
  node_instance_type       = var.node_instance_type
  node_desired_size        = var.node_desired_size
  node_min_size            = var.node_min_size
  node_max_size            = var.node_max_size
  eks_admin_principal_arns = var.eks_admin_principal_arns
}

module "access" {
  source = "../../modules/access"

  region                    = var.region
  cluster_name              = var.cluster_name
  vpc_id                    = module.network.vpc_id
  private_subnet_ids        = module.network.private_subnet_ids
  cluster_security_group_id = module.eks_platform.cluster_security_group_id
  cluster_endpoint          = module.eks_platform.cluster_endpoint
}

module "edge" {
  source = "../../modules/edge"

  cluster_name          = var.cluster_name
  frontend_alb_dns_name = var.frontend_alb_dns_name
}
