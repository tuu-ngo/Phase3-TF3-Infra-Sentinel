# CloudFront Private Origin Migration Runbook

Runbook này chuyển storefront production từ public ALB origin sang CloudFront VPC Origin
và internal ALB. Thực hiện tuần tự; không gộp nhiều phase vào cùng một Terraform apply.

## Bất biến an toàn

- Không sửa flagd, `values-flagd-sync.yaml`, sync token hoặc Envoy fault filter.
- Không xóa public Ingress/ALB trước khi cutover đạt observation gate 60 phút.
- Mỗi apply phải dùng saved plan vừa tạo trong cùng GitHub Actions run.
- Mọi lệnh `kubectl` chạy qua SSM tunnel theo `infra/README.md`.
- `edge_phase` trong `infra/live/production/production.auto.tfvars` là desired state duy
  nhất; không override phase bằng biến môi trường khi apply.

## Phase A - WAF và security boundary

Desired state:

```hcl
edge_phase       = "waf"
private_alb_name = "techx-tf3-frontend-internal"
```

Trigger plan:

```sh
gh workflow run terraform-apply.yml \
  --ref main -f action=plan
gh run list --workflow terraform-apply.yml --branch main --limit 1
```

Chỉ apply khi plan có đúng đặc điểm:

```text
2 to add, 1 to change, 0 to destroy
Add: aws_wafv2_web_acl.frontend, aws_security_group.internal_alb
Change: aws_cloudfront_distribution.frontend.web_acl_id
CloudFront origin domain and origin_id: unchanged
```

Apply saved plan:

```sh
gh workflow run terraform-apply.yml \
  --ref main -f action=apply
```

Chờ workflow hoàn tất rồi kiểm tra:

```sh
aws cloudfront wait distribution-deployed --id E3DLSBEPU1N5UJ

curl -sS -o /dev/null -w 'storefront %{http_code}\n' \
  https://d2tn71186d7ilz.cloudfront.net/

for path in grafana jaeger loadgen feature; do
  curl -sS -o /dev/null -w "$path %{http_code}\n" \
    "https://d2tn71186d7ilz.cloudfront.net/$path/"
done

for path in GRAFANA JAEGER LOADGEN FEATURE; do
  curl -sS -o /dev/null -w "$path %{http_code}\n" \
    "https://d2tn71186d7ilz.cloudfront.net/$path/"
done
```

Expected: storefront `200`; tám operations requests đều `403`.

## Phase B - Internal ALB

Phase A phải hoàn tất trước vì Ingress tham chiếu security group bằng Name tag
`techx-corp-tf3-internal-alb`.

Tạo persistent edge Application:

```sh
kubectl apply -f gitops/apps/techx-edge.yaml
kubectl -n argocd get application techx-edge -w
```

Kiểm tra Ingress và ALB:

```sh
kubectl -n techx-tf3 get ingress frontend-proxy frontend-proxy-internal -o wide

aws elbv2 describe-load-balancers \
  --names techx-tf3-frontend-internal \
  --query 'LoadBalancers[0].{Arn:LoadBalancerArn,DNS:DNSName,Scheme:Scheme,State:State.Code,VpcId:VpcId}'

PRIVATE_ALB_ARN=$(aws elbv2 describe-load-balancers \
  --names techx-tf3-frontend-internal \
  --query 'LoadBalancers[0].LoadBalancerArn' --output text)

TARGET_GROUP_ARN=$(aws elbv2 describe-target-groups \
  --load-balancer-arn "$PRIVATE_ALB_ARN" \
  --query 'TargetGroups[0].TargetGroupArn' --output text)

aws elbv2 describe-target-health --target-group-arn "$TARGET_GROUP_ARN" \
  --query 'TargetHealthDescriptions[].{Target:Target.Id,State:TargetHealth.State,Reason:TargetHealth.Reason}'
```

Gate: scheme `internal`, state `active`, VPC `vpc-0c0b86b42bbbefd55`, tất cả targets
`healthy`. Public Ingress vẫn phải tồn tại.

Từ máy ngoài VPC, DNS internal ALB không được phục vụ HTTP:

```sh
PRIVATE_ALB_DNS=$(aws elbv2 describe-load-balancers \
  --names techx-tf3-frontend-internal \
  --query 'LoadBalancers[0].DNSName' --output text)
curl --connect-timeout 5 "http://$PRIVATE_ALB_DNS/"
```

Expected: timeout hoặc không kết nối được.

## Phase C - VPC Origin và staging

Repo admin tạo GitHub repository secret trước khi đổi phase:

```sh
openssl rand -hex 24 | gh secret set CLOUDFRONT_STAGING_SELECTOR \
  --repo tuu-ngo/Phase3-TF3-Infra-Sentinel
```

Không in, ghi file hoặc commit giá trị này. Đổi tracked desired state:

```hcl
edge_phase = "staging"
```

Commit, push, chạy saved-plan apply như Phase A. Plan phải:

- Tạo một VPC Origin, một staging distribution và một continuous deployment policy.
- Giữ primary distribution trên public ALB origin.
- Không destroy public ALB, EKS hoặc primary distribution.

Apply workflow tự dùng repository secret để chạy smoke test header-routed và chỉ ghi HTTP
status vào log; selector không được echo.

Lấy selector vào shell mà không echo rồi test qua production domain:

```sh
read -rsp 'CloudFront staging selector: ' CLOUDFRONT_STAGING_SELECTOR
printf '\n'

curl -H "aws-cf-cd-techx-private-origin: $CLOUDFRONT_STAGING_SELECTOR" \
  -sS -o /dev/null -w 'staging storefront %{http_code}\n' \
  https://d2tn71186d7ilz.cloudfront.net/

for path in grafana jaeger loadgen feature; do
  curl -H "aws-cf-cd-techx-private-origin: $CLOUDFRONT_STAGING_SELECTOR" \
    -sS -o /dev/null -w "staging $path %{http_code}\n" \
    "https://d2tn71186d7ilz.cloudfront.net/$path/"
done

unset CLOUDFRONT_STAGING_SELECTOR
```

Gate: staging storefront `200`; operations paths `403`; cart, checkout, `/flagservice/*`
và `/otlp-http/*` hoạt động. Request không có selector vẫn dùng public origin.

## Phase D - Primary cutover

Đổi tracked desired state:

```hcl
edge_phase = "private"
```

Commit, push và apply saved plan. Plan phải đổi primary origin sang VPC Origin, gỡ
staging traffic bằng cách đặt continuous deployment policy `enabled=false`, giữ staging
resources cho cleanup riêng, và giữ public Ingress/ALB bên ngoài Terraform nguyên vẹn.

Chờ CloudFront deploy:

```sh
aws cloudfront wait distribution-deployed --id E3DLSBEPU1N5UJ
aws cloudfront get-distribution --id E3DLSBEPU1N5UJ \
  --query 'Distribution.{Status:Status,Domain:DomainName}'
```

Trong 60 phút, theo dõi CloudFront `5xx`, origin latency/errors, ALB healthy host count và
smoke test storefront. Rollback ngay nếu có 502/503/504, 5xx vượt 1% trong 5 phút,
checkout/feature flags lỗi hoặc internal ALB có unhealthy target.

## Rollback trước cleanup

Đổi `edge_phase` thành `rollback`, commit và chạy saved-plan apply. Phase này giữ WAF,
internal ALB security group và VPC Origin nhưng đưa primary CloudFront về public ALB
origin. Không xóa internal ALB/VPC Origin trong cùng thao tác điều tra sự cố.

Sau rollback:

```sh
aws cloudfront wait distribution-deployed --id E3DLSBEPU1N5UJ
curl -sS -o /dev/null -w '%{http_code}\n' \
  https://d2tn71186d7ilz.cloudfront.net/
```

Expected: `200`, cart/checkout/feature flags hoạt động và public target group healthy.

## Phase E - Cleanup

Chỉ thực hiện khi cutover ổn định đủ 60 phút và steady-state đã merge vào `main`:

1. Đổi `gitops/apps/techx-edge.yaml` sang `targetRevision: main`.
2. Đặt `components.frontend-proxy.ingress.enabled: false` trong production Helm values để
   xóa Ingress `frontend-proxy` cũ.
3. Xác minh `frontend-proxy-internal` vẫn được `techx-edge` quản lý và healthy.
4. Chờ AWS Load Balancer Controller xóa public ALB.
5. Chạy Terraform plan và ArgoCD diff; không chấp nhận drift ngoài cleanup dự kiến.

Provider AWS 5.100 giữ `continuous_deployment_policy_id` khi giá trị bị bỏ qua, nên không
xóa staging policy/distribution trong cùng cutover. Cleanup phải detach policy bằng một
plan/API operation riêng đã review, refresh Terraform state, rồi mới destroy staging
resources.

Không xóa `techx-edge` Application hoặc internal Ingress trong cleanup.

## Evidence bắt buộc

Lưu vào deployment record:

- Git commit SHA và GitHub Actions run URL của từng phase.
- Terraform plan summary và checksum artifact.
- CloudFront distribution/VPC Origin status.
- Internal ALB scheme, subnet, security group và target health.
- HTTP status của storefront, runtime routes và operations routes.
- Thời điểm bắt đầu/kết thúc observation gate và quyết định cleanup/rollback.
