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

  cluster_name                = var.cluster_name
  cluster_version             = var.cluster_version
  vpc_id                      = module.network.vpc_id
  private_subnet_ids          = module.network.private_subnet_ids
  node_instance_type          = var.node_instance_type
  node_desired_size           = var.node_desired_size
  node_min_size               = var.node_min_size
  node_max_size               = var.node_max_size
  stateful_node_subnet_id     = module.network.private_subnet_ids[index(var.azs, var.stateful_node_availability_zone)]
  stateful_node_instance_type = var.stateful_node_instance_type
  eks_admin_principal_arns    = var.eks_admin_principal_arns
  eks_kubernetes_group_principals = {
    (aws_iam_role.tf3_production_operator.arn) = ["tf3-production-operators"]
    (aws_iam_role.tf3_production_readonly.arn) = ["tf3-production-readers"]
  }
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

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  cluster_name                = var.cluster_name
  frontend_alb_dns_name       = var.frontend_alb_dns_name
  vpc_id                      = module.network.vpc_id
  private_alb_name            = var.private_alb_name
  edge_phase                  = var.edge_phase
  cloudfront_staging_selector = var.cloudfront_staging_selector
}
