variable "account_id" {
  description = "Cloudflare account ID (Zero Trust org lives under this account)."
  type        = string
}

variable "zone_id" {
  description = "Cloudflare zone ID for the domain the tunnel hostname is created on."
  type        = string
}

variable "zone_name" {
  description = "Domain name matching zone_id, e.g. techx-tf3-ops.com."
  type        = string
}

variable "tunnel_name" {
  description = "Name for the Cloudflare Tunnel (shown in the Zero Trust dashboard)."
  type        = string
  default     = "techx-tf3-eks-api"
}

variable "tunnel_hostname" {
  description = "Public hostname that proxies to the EKS private API endpoint, e.g. kubectl.techx-tf3-ops.com."
  type        = string
}

variable "eks_cluster_endpoint" {
  description = "EKS cluster API server endpoint (https://... form) - the tunnel's ingress target."
  type        = string
}

variable "allowed_email_domain" {
  description = "Email domain allowed to authenticate via SSO for the Access application (e.g. techx-corp.com). Leave empty to use allowed_emails instead."
  type        = string
  default     = ""
}

variable "allowed_emails" {
  description = "Explicit list of emails allowed to authenticate, used when allowed_email_domain is empty."
  type        = list(string)
  default     = []
}

variable "session_duration" {
  description = "How long an authenticated Access session stays valid before re-auth is required."
  type        = string
  default     = "8h"
}

variable "internal_ui_routes" {
  description = <<-EOT
    Direct browser routes to in-cluster HTTP UIs (Grafana, Jaeger, ArgoCD...), bypassing
    kubectl/EKS-API/AWS IAM entirely - cloudflared (running inside the cluster) proxies
    straight to the Service's ClusterIP DNS name. Each entry gets its own hostname, DNS
    record, and Access application+policy (same allowlist as the rest of this module).
    Key = short name used in resource names (e.g. "grafana"). service must be a full
    scheme://host:port the cloudflared pod can reach, e.g.
    "http://grafana.techx-tf3.svc.cluster.local:80".
  EOT
  type = map(object({
    hostname      = string
    service       = string
    no_tls_verify = optional(bool, false)
  }))
  default = {}
}
