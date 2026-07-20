eks_admin_principal_arns = [
  "arn:aws:iam::197826770971:user/cdo-2-admin-team",
]

edge_phase       = "private"
private_alb_name = "techx-tf3-frontend-internal"

enable_cloudflare_access        = true
cloudflare_account_id           = "4903f08491f403370e1a2ae9c8aee84e"
cloudflare_zone_id              = "b711c7ecbcb4efb9d909de520330f0bb"
cloudflare_zone_name            = "arthur-ngo.org"
cloudflare_tunnel_hostname      = "kubectl.arthur-ngo.org"
cloudflare_allowed_email_domain = ""
cloudflare_allowed_emails = [
  "hiimtuu@gmail.com",
  "tutc.work@gmail.com",
  "trongtanaws@gmail.com",
  # Mentors — SSO access tới Grafana/Jaeger/ArgoCD UI qua Cloudflare Zero Trust (REL-17).
  "nghia.huynh@techxcorp.com",
  "toan.le@techxcorp.com",
  "khanh.nguyen@techxcorp.com",
  "namhong.ta@techxcorp.com",
]

# Mandate #8 — bật tầng datastore managed (RDS/ElastiCache/MSK).
# Đặt = true để state khớp hạ tầng thật; nếu để default false, plan sau sẽ đòi XOÁ 3 store.
enable_managed_datastores = true
