output "vpc_id" {
  value = module.network.vpc_id
}

output "private_subnet_ids" {
  value = module.network.private_subnet_ids
}

output "public_subnet_ids" {
  value = module.network.public_subnet_ids
}

output "cluster_name" {
  value = module.eks_platform.cluster_name
}

output "cluster_endpoint" {
  value = module.eks_platform.cluster_endpoint
}

output "cluster_oidc_provider_arn" {
  value = module.eks_platform.oidc_provider_arn
}

output "cluster_autoscaler_role_arn" {
  value = module.eks_platform.cluster_autoscaler_role_arn
}

output "karpenter_controller_role_arn" {
  value = module.eks_platform.karpenter_controller_role_arn
}

output "karpenter_node_role_name" {
  value = module.eks_platform.karpenter_node_role_name
}

output "karpenter_interruption_queue_name" {
  value = module.eks_platform.karpenter_interruption_queue_name
}

output "lb_controller_role_arn" {
  value = module.eks_platform.lb_controller_role_arn
}

output "configure_kubectl" {
  description = "Run this to configure kubectl for the production cluster."
  value       = "aws eks update-kubeconfig --name ${module.eks_platform.cluster_name} --region ${var.region}"
}

output "bastion_instance_id" {
  description = "SSM Session Manager target for private EKS API access."
  value       = module.access.bastion_instance_id
}

output "ssm_tunnel_command" {
  description = "Open the private EKS API tunnel on localhost:8443."
  value       = module.access.ssm_tunnel_command
}

output "cloudfront_domain_name" {
  description = "Public HTTPS address for the storefront."
  value       = module.edge.cloudfront_domain_name
}

output "cloudfront_distribution_id" {
  description = "Primary CloudFront distribution ID."
  value       = module.edge.cloudfront_distribution_id
}

output "internal_alb_security_group_id" {
  description = "Terraform-managed security group for the internal frontend ALB."
  value       = module.edge.internal_alb_security_group_id
}

output "cloudfront_vpc_origin_id" {
  description = "CloudFront VPC Origin ID after the internal origin phase begins."
  value       = module.edge.cloudfront_vpc_origin_id
}
