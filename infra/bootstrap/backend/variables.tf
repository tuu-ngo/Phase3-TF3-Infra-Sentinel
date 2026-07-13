variable "region" {
  type    = string
  default = "ap-southeast-1"
}

variable "state_bucket_name" {
  type    = string
  default = "techx-tf3-197826770971-tfstate"
}

variable "lock_table_name" {
  type    = string
  default = "techx-tf3-terraform-lock"
}
