# Committed (not gitignored, unlike terraform.tfvars) so CI and every team
# member's local `terraform plan` use the same values - no more drift from
# people running apply with their own incomplete local tfvars.
# ARNs here are not secret (account ID + IAM username, already visible in
# CloudTrail/console to anyone with access to this AWS account).

eks_admin_principal_arns = [
  "arn:aws:iam::197826770971:user/cdo-2-admin-team",
  # TODO: thêm ARN IAM user của CDO01 ở account mới 197826770971 vào đây,
  # không thì CDO01 không kubectl/helm vào cluster được.
]

# Account mới là greenfield (không có cluster live để khớp version như account BTC),
# nên tạo thẳng version mới nhất còn standard support để KHÔNG dính phí extended support.
# 1.35 available ở ap-southeast-1 (đã check `aws eks describe-cluster-versions`).
cluster_version = "1.35"

# ALB do aws-load-balancer-controller tạo từ Ingress frontend-proxy (Cách A).
# CloudFront (cloudfront.tf) trỏ origin vào đây. Cập nhật nếu Ingress bị tạo lại.
frontend_alb_dns_name = "k8s-techxtf3-frontend-3153771b08-956551046.ap-southeast-1.elb.amazonaws.com"
