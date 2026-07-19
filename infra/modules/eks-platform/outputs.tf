output "cluster_name" {
  value = module.eks.cluster_name
}

output "cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "cluster_security_group_id" {
  value = module.eks.cluster_security_group_id
}

# SG gan len ENI cua node/pod (VPC CNI). Day moi la SG traffic pod thuc su di ra
# -> managed datastore phai allow SG nay thi pod moi noi duoc (cluster SG o tren KHONG
# nam tren node ENI). Xem infra/live/production/main.tf module "datastores".
output "node_security_group_id" {
  value = module.eks.node_security_group_id
}

output "oidc_provider_arn" {
  value = module.eks.oidc_provider_arn
}

output "cluster_autoscaler_role_arn" {
  value = module.cluster_autoscaler_irsa.iam_role_arn
}

output "karpenter_controller_role_arn" {
  value = aws_iam_role.karpenter_controller.arn
}

output "karpenter_node_role_name" {
  value = aws_iam_role.karpenter_node.name
}

output "karpenter_interruption_queue_name" {
  value = aws_sqs_queue.karpenter_interruption.name
}

output "lb_controller_role_arn" {
  value = module.lb_controller_irsa.iam_role_arn
}

output "external_secrets_role_arn" {
  value = aws_iam_role.external_secrets.arn
}

output "external_secrets_role_name" {
  value = aws_iam_role.external_secrets.name
}

output "product_reviews_bedrock_role_arn" {
  value = aws_iam_role.product_reviews_bedrock.arn
}

output "flagd_sync_secret_name" {
  value = aws_secretsmanager_secret.flagd_sync_token.name
}
