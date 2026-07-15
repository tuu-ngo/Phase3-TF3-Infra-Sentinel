provider "aws" {
  region = var.region

  default_tags {
    tags = {
      project    = "techx-corp-phase3"
      team       = "TF3"
      managed-by = "terraform"
    }
  }
}

provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = {
      project    = "techx-corp-phase3"
      team       = "TF3"
      managed-by = "terraform"
    }
  }
}

# REL-17: no api_token argument on purpose - the provider reads CLOUDFLARE_API_TOKEN
# from the environment. Never put the token in a .tf/.tfvars file that gets committed.
# Lazily configured: with enable_cloudflare_access = false (default), module
# "cloudflare_access" has count = 0, so this provider never makes an API call and
# terraform plan/apply work fine even with no token set (CI included).
provider "cloudflare" {}
