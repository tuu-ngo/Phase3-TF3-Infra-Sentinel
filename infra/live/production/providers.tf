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
