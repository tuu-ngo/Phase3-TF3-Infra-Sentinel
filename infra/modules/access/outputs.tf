output "bastion_instance_id" {
  value = aws_instance.bastion.id
}

output "ssm_tunnel_command" {
  value = "aws ssm start-session --target ${aws_instance.bastion.id} --document-name AWS-StartPortForwardingSessionToRemoteHost --parameters host=\"${replace(var.cluster_endpoint, "https://", "")}\",portNumber=\"443\",localPortNumber=\"8443\" --region ${var.region}"
}
