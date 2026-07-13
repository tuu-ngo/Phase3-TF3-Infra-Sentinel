# Runbook — Deploy đầy đủ TechX Corp lên account MỚI (197826770971) tới trạng thái LIVE

**Mục tiêu:** dựng cả stack trên account mới `197826770971` — EKS + app + ALB + CloudFront —
đến khi storefront truy cập được qua HTTPS, **không đụng** hệ thống account cũ (BTC `012619468490`).

**Nhánh:** `deploy/new-account-197826770971` (không merge `main`).
**Profile AWS:** `techx-new` (đặt `set AWS_PROFILE=techx-new` ở MỌI terminal).

> ⚠️ flagd: KHÔNG gỡ/đổi hướng flagd, KHÔNG đổi URI/token nguồn trung tâm. Token chỉ nằm trong
> k8s secret `flagd-sync-token`, không bao giờ commit. Vi phạm = disqualify cả TF3.

---

## PHASE 0 — Prereqs (account mới, làm 1 lần)

```cmd
set AWS_PROFILE=techx-new
aws sts get-caller-identity          REM phải ra 197826770971

REM State backend
aws s3 mb s3://techx-tf3-197826770971-tfstate --region ap-southeast-1
aws s3api put-bucket-versioning --bucket techx-tf3-197826770971-tfstate --versioning-configuration Status=Enabled
aws dynamodb create-table --table-name techx-tf3-terraform-lock --attribute-definitions AttributeName=LockID,AttributeType=S --key-schema AttributeName=LockID,KeyType=HASH --billing-mode PAY_PER_REQUEST --region ap-southeast-1

REM ECR repo (CDO01 push image vào đây)
aws ecr create-repository --repository-name techx-corp --region ap-southeast-1

REM *** BLOCKER: quota vCPU EC2 phải >= 12 (3x t3.large = 6, dư cho autoscale toi 6 node) ***
aws service-quotas get-service-quota --service-code ec2 --quota-code L-1216C47A --region ap-southeast-1 --query "Quota.Value"
```

**Cổng kiểm tra Phase 0 — phải đạt hết trước khi sang Phase 1:**
- [ ] `get-caller-identity` = account 197826770971
- [ ] quota vCPU ≥ 12 (nếu < 12 → mở ticket tăng quota, chờ AWS duyệt, ĐỪNG apply trước)
- [ ] **CDO01 xác nhận image đã ở ECR + cho biết TAG chính xác** (xem Phase 3 — tag phải khớp)

---

## PHASE 1 — Terraform: cluster + IRSA + bastion

`ci.tf` và `cloudfront.tf` đã đổi tên `.disabled` (CI cần OIDC provider chưa có; CloudFront cần ALB
DNS chưa có). Chỉ dựng: VPC, **EKS 1.35** (greenfield, tránh extended-support; set trong
`ci.auto.tfvars`), node group 3×t3.large, 2 IRSA role, bastion, VPC endpoints. **77 resource, 0 destroy.**

```cmd
cd "C:\Users\Admin\Documents\TF3 - Phase 3\infra"
set AWS_PROFILE=techx-new
terraform init -reconfigure -backend-config=backend.new-account.hcl
terraform plan -out=tfplan
```

**Cổng kiểm tra plan — đọc kỹ trước khi apply:**
- [ ] Chỉ có ADD, không DESTROY/replace gì (đây là account trống nên toàn Create).
- [ ] KHÔNG thấy resource `aws_cloudfront_*` hay `aws_iam_role.terraform_*` (đã disable đúng).
- [ ] EKS access entry trỏ ARN `197826770971:user/cdo-2-admin-team` (không phải account cũ).

```cmd
terraform apply tfplan            REM ~18-20 phút
```

Ghi lại output (dùng ở phase sau):
```cmd
terraform output cluster_autoscaler_role_arn
terraform output lb_controller_role_arn
terraform output vpc_id
terraform output ssm_tunnel_command
```

---

## PHASE 2 — Truy cập cluster qua bastion (SSM tunnel)

> Chờ ~2-3 phút sau apply để SSM agent trên bastion đăng ký. Kiểm tra:
> `aws ssm describe-instance-information --query "InstanceInformationList[].InstanceId"` — phải thấy bastion.

**Terminal A** (giữ mở — chính là output `ssm_tunnel_command`):
```cmd
set AWS_PROFILE=techx-new
aws ssm start-session --target <bastion_instance_id> --document-name AWS-StartPortForwardingSessionToRemoteHost --parameters host="<cluster_endpoint bỏ https://>",portNumber="443",localPortNumber="8443" --region ap-southeast-1
```

**Terminal B**:
```cmd
set AWS_PROFILE=techx-new
aws eks update-kubeconfig --name techx-corp-tf3 --region ap-southeast-1
kubectl config set-cluster arn:aws:eks:ap-southeast-1:197826770971:cluster/techx-corp-tf3 --server=https://localhost:8443 --insecure-skip-tls-verify=true
kubectl get nodes
```

**Cổng kiểm tra:** `kubectl get nodes` → 3 node `Ready`.

---

## PHASE 3 — Deploy app (Helm)

### 3.1 Khớp TAG image (điểm sai chí mạng #2) — ĐÃ XÁC ĐỊNH
`values-prod.yaml` đặt `default.image.tag: d2bc367`, NHƯNG CDO01 đang push tag **`58b13f2`**
(git SHA). → **KHÔNG sửa file**, override lúc helm bằng `--set default.image.tag=58b13f2`.

Trước khi deploy, xác nhận CDO01 đã push ĐỦ ~20 image:
```cmd
aws ecr list-images --repository-name techx-corp --region ap-southeast-1 --query "imageIds[].imageTag" --output text
```
Đếm đủ 20 service (`58b13f2-frontend`, `-checkout`, `-product-catalog`, ... `-frontend-proxy`).
Thiếu image nào → pod đó `ImagePullBackOff`. Đợi CDO01 push xong hết rồi mới deploy.

### 3.2 Tạo namespace + secret flagd (token thật, KHÔNG commit)
```cmd
kubectl create namespace techx-tf3
kubectl -n techx-tf3 create secret generic flagd-sync-token --from-literal=token=<REAL_FLAGD_TOKEN>
```

### 3.3 Deploy
> Chỉ `values-prod.yaml`. KHÔNG thêm `values-observability.yaml`/`values-app-stamp.yaml`
> (chart default đã bật app + observability; ghép 2 file kia sẽ tắt hết pod — xem CLAUDE.md).
> `values-prod.yaml` đã chứa lệnh flagd sync trung tâm dùng `$(FLAGD_SYNC_TOKEN)` từ secret trên.

```cmd
helm upgrade --install techx-corp "C:\Users\Admin\Documents\TF3 - Phase 3\phase3 - information\techx-corp-chart" -n techx-tf3 --create-namespace -f "C:\Users\Admin\Documents\TF3 - Phase 3\phase3 - information\deploy\values-prod.yaml" --set default.image.tag=58b13f2
```

**Cổng kiểm tra:**
- [ ] `kubectl -n techx-tf3 get pods` → tất cả `Running`/`Ready`, không `ImagePullBackOff`/`CrashLoop`.
- [ ] **flagd sync đúng nguồn trung tâm (bắt buộc, chống disqualify):**
      `kubectl -n techx-tf3 logs deploy/flagd | findstr /I "sync http"` → thấy sync từ
      `122.248.223.194.sslip.io`, KHÔNG phải file local.
- [ ] Storefront nội bộ OK: `kubectl -n techx-tf3 port-forward svc/frontend-proxy 8080:8080`
      → mở http://localhost:8080 thấy sản phẩm.

---

## PHASE 4 — aws-load-balancer-controller + ALB (điểm sai chí mạng #1)

Không có controller này thì Ingress `frontend-proxy` (class `alb`, internet-facing) KHÔNG tạo ALB.

```cmd
helm repo add eks https://aws.github.io/eks-charts
helm repo update
helm install aws-load-balancer-controller eks/aws-load-balancer-controller -n kube-system --set clusterName=techx-corp-tf3 --set serviceAccount.create=true --set serviceAccount.name=aws-load-balancer-controller --set serviceAccount.annotations."eks\.amazonaws\.com/role-arn"=<lb_controller_role_arn từ Phase 1> --set region=ap-southeast-1 --set vpcId=<vpc_id từ Phase 1>
```

**Cổng kiểm tra:**
- [ ] `kubectl -n kube-system get deploy aws-load-balancer-controller` → Ready 2/2.
- [ ] Sau ~2-3 phút: `kubectl -n techx-tf3 get ingress` → cột ADDRESS có DNS ALB
      (`k8s-techxtf3-...elb.amazonaws.com`).
- [ ] `curl http://<ALB_DNS>/` → 200, HTML storefront. **Ghi lại ALB_DNS cho Phase 5.**

> Nếu ADDRESS trống sau 5 phút: xem `kubectl -n kube-system logs deploy/aws-load-balancer-controller`.
> Nguyên nhân hay gặp: sai role ARN (IRSA), hoặc subnet public thiếu tag `kubernetes.io/role/elb=1`
> (networking.tf đã set sẵn — không nên xảy ra).

---

## PHASE 5 — CloudFront (HTTPS công khai)

Giờ đã có ALB DNS → bật lại CloudFront, trỏ origin vào ALB đó.

```cmd
cd "C:\Users\Admin\Documents\TF3 - Phase 3\infra"
git mv cloudfront.tf.disabled cloudfront.tf
```
Điền `frontend_alb_dns_name` vào `terraform.tfvars` (tạo nếu chưa có):
```hcl
frontend_alb_dns_name = "<ALB_DNS từ Phase 4>"
```
```cmd
terraform plan -out=tfplan       REM chỉ thấy ADD aws_cloudfront_distribution
terraform apply tfplan
terraform output cloudfront_domain_name
```

**Cổng kiểm tra (LIVE):**
- [ ] CloudFront `Deployed` (~5-15 phút để phân phối toàn cầu).
- [ ] Mở `https://<xxxx>.cloudfront.net` → storefront qua HTTPS, review có tóm tắt AI.

---

## Trạng thái sau Phase 5 = HỆ THỐNG LIVE
Storefront: `https://<cloudfront>.cloudfront.net` · ops (Grafana/Jaeger) qua port-forward (giữ private).

## Phase 6 (tách riêng — mandate autoscale, không bắt buộc để "live")
metrics-server + HPA + cluster-autoscaler. Các file `gitops/` là ArgoCD Application; account mới
CHƯA có ArgoCD → hoặc cài ArgoCD trước, hoặc dịch sang cài tay (helm metrics-server + cluster-autoscaler,
`kubectl apply -f gitops/infrastructure/{hpa-hotpath,pdb-checkout,limit-range,resource-quota}.yaml`).
Lưu ý: managed node group ASG cần tag `k8s.io/cluster-autoscaler/enabled` để CA autodiscover —
kiểm tra trước khi test flash sale.

## Teardown (sau khi lấy xong evidence — tiết kiệm cost)
```cmd
helm uninstall techx-corp -n techx-tf3
cd infra && terraform destroy      REM xoá sạch account mới; account cũ không ảnh hưởng
```

## Quay lại account cũ khi BTC unblock
```cmd
set AWS_PROFILE=default
git checkout main
cd infra && terraform init -reconfigure -backend-config=backend.hcl
```
