eks_admin_principal_arns = [
  "arn:aws:iam::197826770971:user/cdo-2-admin-team",
]

edge_phase       = "private"
private_alb_name = "techx-tf3-frontend-internal"

enable_cloudflare_access        = true
cloudflare_zone_name            = "arthur-ngo.org"
cloudflare_tunnel_hostname      = "kubectl.arthur-ngo.org"
cloudflare_allowed_email_domain = ""
