# REL-17: SSO-based replacement/augmentation for the SSM-bastion tunnel to the private
# EKS API. cloudflared runs as a Deployment inside the cluster (it already has network
# reach to the API server the same way kubelet does - no security-group change needed,
# unlike the bastion) and dials OUT to Cloudflare's edge, so this keeps the same
# 0-inbound-port posture the SSM bastion already has. Auth moves from a static IAM user
# to SSO+MFA via Cloudflare Access, scoped per-application instead of whole-cluster IAM.
#
# The SSM bastion (module "access") is NOT removed by this module - it stays as fallback
# until this path is verified stable in real day-to-day use.

resource "random_id" "tunnel_secret" {
  byte_length = 32
}

resource "cloudflare_zero_trust_tunnel_cloudflared" "eks_api" {
  account_id = var.account_id
  name       = var.tunnel_name
  secret     = random_id.tunnel_secret.b64_std
}

resource "cloudflare_zero_trust_tunnel_cloudflared_config" "eks_api" {
  account_id = var.account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.eks_api.id

  config {
    ingress_rule {
      hostname = var.tunnel_hostname
      service  = "tcp://${replace(var.eks_cluster_endpoint, "https://", "")}:443"
    }

    # catch-all - required by the provider, anything not matching the rule above is dropped
    ingress_rule {
      service = "http_status:404"
    }
  }
}

resource "cloudflare_record" "eks_api" {
  zone_id = var.zone_id
  name    = trimsuffix(var.tunnel_hostname, ".${var.zone_name}")
  type    = "CNAME"
  content = "${cloudflare_zero_trust_tunnel_cloudflared.eks_api.id}.cfargotunnel.com"
  proxied = true
}

resource "cloudflare_zero_trust_access_application" "eks_api" {
  account_id       = var.account_id
  name             = "${var.tunnel_name}-kubectl"
  domain           = var.tunnel_hostname
  type             = "self_hosted"
  session_duration = var.session_duration
}

resource "cloudflare_zero_trust_access_policy" "eks_api_allow" {
  account_id     = var.account_id
  application_id = cloudflare_zero_trust_access_application.eks_api.id
  name           = "${var.tunnel_name}-sso-allow"
  precedence     = 1
  decision       = "allow"

  include {
    email_domain = var.allowed_email_domain != "" ? [var.allowed_email_domain] : []
    email        = var.allowed_email_domain == "" ? var.allowed_emails : []
  }
}
