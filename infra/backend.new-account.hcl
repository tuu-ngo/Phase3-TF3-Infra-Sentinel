# Backend cho account MỚI 197826770971 (CDO01+CDO02 dựng lại song song).
# KHÔNG đè backend.hcl (đang trỏ state account BTC 012619468490).
# Dùng:  terraform init -reconfigure -backend-config=backend.new-account.hcl
# (-reconfigure: bỏ backend cũ, KHÔNG migrate state BTC sang đây.)
bucket         = "techx-tf3-197826770971-tfstate"
key            = "eks-baseline/terraform.tfstate"
region         = "ap-southeast-1"
dynamodb_table = "techx-tf3-terraform-lock"
encrypt        = true
