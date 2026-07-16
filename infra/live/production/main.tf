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

# ── Mandate 08: AWS Managed Datastores ──────────────────────────────────────
# Provisions RDS PostgreSQL, ElastiCache Redis, and MSK Kafka as private,
# encrypted, fully managed replacements for the in-cluster datastores.
# See docs/adr/0002-managed-services-evaluation.md for decision record.
module "managed_datastores" {
  source = "../../modules/managed-datastores"

  cluster_name               = var.cluster_name
  vpc_id                     = module.network.vpc_id
  private_subnet_ids         = module.network.private_subnet_ids
  vpc_cidr                   = var.vpc_cidr
  eks_node_security_group_id = module.eks_platform.node_security_group_id

  rds_instance_class      = var.rds_instance_class
  rds_db_name             = var.rds_db_name
  rds_engine_version      = var.rds_engine_version
  rds_multi_az            = var.rds_multi_az
  rds_deletion_protection = var.rds_deletion_protection

  elasticache_node_type      = var.elasticache_node_type
  elasticache_engine_version = var.elasticache_engine_version

  msk_instance_type          = var.msk_instance_type
  msk_kafka_version          = var.msk_kafka_version
  msk_number_of_broker_nodes = var.msk_number_of_broker_nodes
}
