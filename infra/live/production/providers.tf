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
