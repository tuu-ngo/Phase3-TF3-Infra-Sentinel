# REL-17 - see docs/backlog/cdo02-reliability-cost-backlog.md and
# docs/runbooks/cloudflare-zero-trust-access.md. Inert by default (count = 0) until
# enable_cloudflare_access = true and the cloudflare_* variables are filled in.
module "cloudflare_access" {
  source = "../../modules/cloudflare-access"
  count  = var.enable_cloudflare_access ? 1 : 0

  account_id           = var.cloudflare_account_id
  zone_id              = var.cloudflare_zone_id
  zone_name            = var.cloudflare_zone_name
  tunnel_hostname      = var.cloudflare_tunnel_hostname
  eks_cluster_endpoint = module.eks_platform.cluster_endpoint
  allowed_email_domain = var.cloudflare_allowed_email_domain
  allowed_emails       = var.cloudflare_allowed_emails
}
