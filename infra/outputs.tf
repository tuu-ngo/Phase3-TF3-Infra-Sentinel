output "vpc_id" {
  value = module.vpc.vpc_id
}

output "private_subnet_ids" {
  value = module.vpc.private_subnets
}

output "public_subnet_ids" {
  value = module.vpc.public_subnets
}

output "cluster_name" {
  value = module.eks.cluster_name
}

output "cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "cluster_oidc_provider_arn" {
  value = module.eks.oidc_provider_arn
}

output "cluster_autoscaler_role_arn" {
  value = module.cluster_autoscaler_irsa.iam_role_arn
}

output "lb_controller_role_arn" {
  value = module.lb_controller_irsa.iam_role_arn
}

output "configure_kubectl" {
  description = "Run this after apply to point kubectl/helm at the new cluster"
  value       = "aws eks update-kubeconfig --name ${module.eks.cluster_name} --region ${var.region}"
}

output "product_reviews_role_arn" {
  value = module.product_reviews_irsa.iam_role_arn
}

