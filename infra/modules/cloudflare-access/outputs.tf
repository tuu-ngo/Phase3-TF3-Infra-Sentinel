output "tunnel_id" {
  value = cloudflare_zero_trust_tunnel_cloudflared.eks_api.id
}

output "tunnel_token" {
  description = "Pass to `cloudflared tunnel run --token <this>` (in-cluster Deployment) or write straight into the Kubernetes Secret. Never commit this value."
  value       = cloudflare_zero_trust_tunnel_cloudflared.eks_api.tunnel_token
  sensitive   = true
}

output "tunnel_hostname" {
  value = var.tunnel_hostname
}

output "client_access_command" {
  description = "Command each team member runs locally instead of `aws ssm start-session`."
  value       = "cloudflared access tcp --hostname ${var.tunnel_hostname} --url 127.0.0.1:8443"
}
