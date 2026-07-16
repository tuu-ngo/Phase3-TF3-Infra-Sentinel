# Terraform infrastructure

Production của TF3 nằm trong AWS account `197826770971`, region `ap-southeast-1`.
EKS API private-only và chỉ truy cập qua SSM bastion.

## Cấu trúc

```text
infra/
├── bootstrap/
│   ├── backend/       # ownership S3 state bucket + DynamoDB lock table
│   └── github-oidc/   # ownership IAM roles cho GitHub Actions
├── live/production/   # production root duy nhất
└── modules/
    ├── network/       # VPC, NAT, S3/ECR/SSM endpoints
    ├── eks-platform/  # KMS, EKS, node group, add-ons, IRSA
    ├── access/        # private SSM bastion
    └── edge/          # CloudFront
```

Hai root trong `bootstrap/` chỉ mô tả ownership. Resource đã tồn tại nên **không apply/import**
chúng nếu chưa có một kế hoạch adoption và phê duyệt riêng. Workflow production không chạy
hai root này.

## Init và plan production

```sh
cd infra/live/production
terraform init -reconfigure -backend-config=backend.hcl.example
terraform fmt -check -recursive ../../
terraform validate
terraform plan -lock=false
```

`production.auto.tfvars` chứa principal EKS của account hiện tại. Push thay đổi Terraform vào
`main` sẽ chạy workflow plan. Workflow apply chỉ chạy thủ công trên protected `main` và phải qua
GitHub Environment `production`:

```sh
# Chỉ tạo và kiểm tra saved plan
gh workflow run terraform-apply.yml \
  --ref main -f action=plan

# Tạo saved plan mới rồi apply chính plan đó
gh workflow run terraform-apply.yml \
  --ref main -f action=apply
```

Chỉ chọn `action=apply` sau khi saved plan trong chính run đó đã được review. Apply role hiện vẫn
có `AdministratorAccess`; thu hẹp role là hardening còn mở, không được gộp vào một apply production
không liên quan.

## CloudFront private origin migration

`edge_phase` trong `live/production/production.auto.tfvars` điều khiển migration theo thứ tự:

| Phase | Primary origin | Tài nguyên thêm |
|---|---|---|
| `public` | Public ALB | Không |
| `waf` | Public ALB | WAF + internal ALB security group |
| `staging` | Public ALB | Internal VPC Origin + staging distribution |
| `private` | Internal ALB qua VPC Origin | Giữ staging resources, policy disabled |
| `rollback` | Public ALB | Giữ WAF, VPC Origin và staging resources, policy disabled |

Không nhảy phase và không override `edge_phase` khi apply. Runbook đầy đủ, quality gates và
rollback: [`docs/runbooks/cloudfront-private-origin-migration.md`](../docs/runbooks/cloudfront-private-origin-migration.md).

## Truy cập cluster qua SSM bastion

EKS API **đã chuyển private-only** (`cluster_endpoint_public_access = false`) — không còn IP
allowlist nào để quản lý nữa (lý do: nhiều lần bị đè mất CIDR do nhiều người tự `apply`, xem
`docs/postmortem/`). Muốn `kubectl`/`helm`, mọi người đi qua bastion trong module `access`
bằng SSM, không cần IP tĩnh hay CIDR allowlist:

```sh
# Bước 1: mở tunnel (giữ terminal này chạy)
aws ssm start-session --target <bastion_instance_id, xem terraform output bastion_instance_id> \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters host="<cluster_endpoint không có https://, xem terraform output cluster_endpoint>",portNumber="443",localPortNumber="8443" \
  --region ap-southeast-1

# Bước 2 (terminal khác): trỏ kubectl vào tunnel
aws eks update-kubeconfig --name techx-corp-tf3 --region ap-southeast-1
kubectl config set-cluster arn:aws:eks:ap-southeast-1:197826770971:cluster/techx-corp-tf3 \
  --server=https://localhost:8443 --insecure-skip-tls-verify=true

kubectl get nodes   # phải thấy 3 node Ready
```

`--insecure-skip-tls-verify` cần thiết vì chứng chỉ TLS của cluster cấp cho hostname thật, không
phải `localhost` — chấp nhận được vì traffic đã đi trong tunnel mã hoá của SSM.

Lệnh đầy đủ (đã điền sẵn ID) có thể lấy lại từ production root:
```sh
cd infra/live/production
terraform output ssm_tunnel_command
```

**Yêu cầu để dùng được**: IAM principal cần quyền gọi `ssm:StartSession` trên bastion và
phải có mặt trong `eks_admin_principal_arns` để xác thực với EKS.

Từ đây tiếp tục theo [`GETTING_STARTED.md`](../phase3%20-%20information/GETTING_STARTED.md)
mục 2-5 (helm repo add, dependency build, `helm upgrade --install`).

## Chưa nằm trong phạm vi apply này (cố ý)

- Chart `aws-load-balancer-controller` / `cluster-autoscaler` - IAM role (IRSA) đã
  chuẩn bị sẵn (xem output `cluster_autoscaler_role_arn` / `lb_controller_role_arn`),
  nhưng việc `helm install` 2 add-on này làm riêng sau, không phải lúc apply Terraform.
- Migrate Postgres/Valkey/Kafka sang managed (RDS/ElastiCache/MSK) - nằm ngoài baseline,
  chỉ làm khi có mandate hoặc backlog ưu tiên tới lượt.

## Đổi số NAT Gateway / node sau này

Nếu backlog quyết định cần thêm NAT hoặc đổi instance type, sửa input ở production root,
review plan qua PR và ghi ADR kèm lý do vì đây là thay đổi tốn tiền theo `RULES.md`.
