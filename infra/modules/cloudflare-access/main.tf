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

    # UI routes go straight to the in-cluster Service - no EKS API, no AWS IAM in this
    # path at all. Must come before the catch-all below (ingress rules are first-match).
    dynamic "ingress_rule" {
      for_each = var.internal_ui_routes
      content {
        hostname = ingress_rule.value.hostname
        service  = ingress_rule.value.service

        dynamic "origin_request" {
          for_each = ingress_rule.value.no_tls_verify ? [1] : []
          content {
            no_tls_verify = true
          }
        }
      }
    }

    # catch-all - required by the provider, anything not matching the rules above is dropped
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

resource "cloudflare_record" "internal_ui" {
  for_each = var.internal_ui_routes

  zone_id = var.zone_id
  name    = trimsuffix(each.value.hostname, ".${var.zone_name}")
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

resource "cloudflare_zero_trust_access_application" "internal_ui" {
  for_each = var.internal_ui_routes

  account_id       = var.account_id
  name             = "${var.tunnel_name}-${each.key}"
  domain           = each.value.hostname
  type             = "self_hosted"
  session_duration = var.session_duration
}

resource "cloudflare_zero_trust_access_policy" "internal_ui_allow" {
  for_each = var.internal_ui_routes

  account_id     = var.account_id
  application_id = cloudflare_zero_trust_access_application.internal_ui[each.key].id
  name           = "${var.tunnel_name}-${each.key}-sso-allow"
  precedence     = 1
  decision       = "allow"

  include {
    email_domain = var.allowed_email_domain != "" ? [var.allowed_email_domain] : []
    email        = var.allowed_email_domain == "" ? var.allowed_emails : []
  }
}
