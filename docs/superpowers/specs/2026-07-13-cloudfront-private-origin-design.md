# CloudFront Private Origin Hardening Design

## 1. Muc tieu

Chuyen storefront production sang luong truy cap duy nhat:

```text
Internet -> CloudFront + AWS WAF -> CloudFront VPC Origin
         -> internal ALB -> frontend-proxy -> services
```

Sau migration:

- Khach hang khong the truy cap ALB truc tiep tu Internet.
- CloudFront la public entry point duy nhat.
- `/grafana*`, `/jaeger*`, `/loadgen*`, `/feature*` bi chan tai CloudFront voi HTTP 403.
- `/flagservice/*` va `/otlp-http/*` van public vi storefront can feature flags va browser telemetry.
- Doi van han van truy cap Grafana, Jaeger, Load Generator va Feature UI qua SSM bastion + `kubectl port-forward`.
- Storefront khong downtime trong qua trinh migration.

## 2. Hien trang da xac minh

- CloudFront distribution `E3DLSBEPU1N5UJ` dang tro toi ALB `internet-facing`.
- ALB security group dang cho phep TCP/80 tu `0.0.0.0/0`.
- Ca CloudFront va ALB DNS deu tra HTTP 200 cho storefront, Grafana, Jaeger va Load Generator.
- EKS API la private-only; duong quan tri la SSM bastion.
- AWS Load Balancer Controller dang quan ly Ingress/ALB.
- ArgoCD application production dang theo doi `main` va bat `prune` + `selfHeal`.
- Terraform AWS provider hien tai ho tro `aws_cloudfront_vpc_origin`, `vpc_origin_config`,
  `aws_cloudfront_continuous_deployment_policy` va AWS WAFv2.

## 3. Quyet dinh kien truc

Dung internal ALB song song voi public ALB hien tai, sau do chuyen CloudFront bang
continuous deployment. Khong doi truc tiep annotation cua Ingress hien tai, vi thay
`internet-facing` bang `internal` se thay ALB va tao khoang origin khong san sang.

Hai phuong an khong chon:

- Doi ALB tai cho: it thay doi hon nhung khong dat zero downtime.
- Giu public ALB va chi gioi han CloudFront prefix list: giam kha nang bypass nhung ALB
  van la internet-facing, khong dat muc tieu private origin.

## 4. Ownership

### Terraform

Terraform quan ly:

- Security group cua internal ALB.
- CloudFront VPC Origin.
- CloudFront staging distribution va continuous deployment policy.
- AWS WAF WebACL scope `CLOUDFRONT` tai `us-east-1`.
- Primary CloudFront distribution va qua trinh cutover declarative.

Module `edge` se nhan VPC ID, ten ALB on dinh va co che bat/tat private origin theo tung
phase. Terraform tim ALB bang ten on dinh sau khi ArgoCD tao xong; khong commit ARN ALB
dong vao source code.

### ArgoCD

ArgoCD quan ly mot edge Application rieng ten `techx-edge`. Trong migration, Application
nay theo nhanh `deploy/account-migration-gitops`; sau khi merge, cung Application chuyen
ve `main`. Application chi quan ly standalone internal Ingress tro toi Service
`frontend-proxy`, khong tao Helm release thu hai va khong tranh ownership voi application
`techx-corp`.

Internal Ingress dung:

- Ten ALB on dinh: `techx-tf3-frontend-internal`.
- Scheme `internal`.
- Ba private subnet hien co.
- Target type `ip`, listener HTTP/80 va health check `/`.
- Security group do Terraform tao.
- Controller duoc phep quan ly backend security-group rules can thiet cho pod targets.

Security group ID la environment identifier, khong phai secret. Sau Phase A, output nay
duoc ghi vao manifest production tren nhanh migration va review truoc khi sync.

Sau khi thay doi steady-state duoc merge vao `main`, bootstrap Application quan ly cung
`techx-edge` Application. Internal Ingress giu nguyen owner va khong bi xoa/tao lai.

## 5. Security controls

### Origin isolation

Trong bootstrap phase, security group cua internal ALB chi nhan TCP/80 tu AWS-managed
CloudFront origin-facing prefix list. Sau khi VPC Origin tao service-managed security
group, rule duoc thu hep ve security group nay neu AWS da san sang resource do.

Internal ALB nam trong private subnet va khong co public route. Khong cho phep CIDR
`0.0.0.0/0`, IP ca nhan hay bastion security group vao listener ALB.

### Edge path policy

AWS WAF WebACL co default action `allow` va mot rule `block-operations-paths`. Rule
inspect URI path sau bien doi lowercase, dung `STARTS_WITH` cho:

- `/grafana`
- `/jaeger`
- `/loadgen`
- `/feature`

Rule bat CloudWatch metrics va sampled requests. Khong chan `/flagservice` va
`/otlp-http`.

WebACL phai duoc gan vao primary distribution truoc khi bat CloudFront continuous
deployment. CloudFront khong cho gan WebACL lan dau trong khi continuous deployment
policy dang active.

## 6. Trinh tu migration zero-downtime

### Phase A - Edge guard va ALB boundary

1. Terraform tao internal ALB security group va WAF WebACL.
2. Terraform gan WebACL vao primary distribution dang dung public origin.
3. Xac minh bon operations path tra 403 qua CloudFront, storefront runtime van hoat dong.

Public ALB van ton tai va la rollback origin trong phase nay.

### Phase B - Internal origin

1. Tao `techx-edge` ArgoCD Application tu nhanh migration.
2. ArgoCD tao standalone internal Ingress va ALB.
3. Cho ALB `active`; tat ca target cua `frontend-proxy` phai `healthy`.
4. Terraform lookup ALB bang ten on dinh va tao CloudFront VPC Origin.
5. Cho VPC Origin dat trang thai `Deployed`.

### Phase C - Staging validation

1. Terraform tao staging distribution voi cung behavior cua primary, nhung origin la
   VPC Origin.
2. Tao header-based continuous deployment policy. Header name bat dau bang
   `aws-cf-cd-`; gia tri test duoc truyen qua GitHub Environment secret, khong commit.
3. Gan policy vao primary distribution.
4. Smoke test qua domain production voi header test de CloudFront route co dinh sang
   staging. Request khong co header tiep tuc dung public origin.

### Phase D - Cutover

1. Sau khi staging dat tat ca quality gate, Terraform doi primary distribution sang
   VPC Origin va tat continuous deployment policy.
2. CloudFront deploy configuration moi; public ALB van duoc giu nguyen lam rollback.
3. Theo doi production lien tuc 60 phut.

### Phase E - Cleanup

1. Merge cau hinh steady-state vao `main`, chuyen `techx-edge` ve `main` va xac minh
   bootstrap Application quan ly no.
2. Xoa public Ingress de AWS Load Balancer Controller xoa public ALB.
3. Xoa staging distribution va continuous deployment policy; giu `techx-edge` de quan
   ly internal Ingress lau dai.
4. Thu hep internal ALB ingress tu prefix list sang CloudFront service-managed security
   group neu resource da duoc tao va xac minh.
5. Chay Terraform plan va ArgoCD diff lan cuoi; khong duoc con drift ngoai du kien.

## 7. Quality gates

### Plan gate

- Terraform plan truoc cutover khong destroy primary distribution hay EKS.
- ArgoCD diff phase B chi add `techx-edge` Application va internal Ingress; khong remove
  public Ingress.
- Khong thay doi flagd, sync token, secrets, Envoy fault filter hay workload deployment.

### Origin gate

- Internal ALB `active` tren private subnets.
- Tat ca targets `healthy`.
- VPC Origin `Deployed`.
- Internal ALB khong truy cap duoc tu Internet.

### Functional gate

- `/` va static assets tra 200.
- Storefront browse, cart va checkout hoat dong.
- Browser feature flags qua `/flagservice/*` hoat dong.
- Browser telemetry qua `/otlp-http/*` khong bi WAF chan.
- Bon operations path tra 403 voi ca chu thuong va bien the chu hoa.
- Doi van han van truy cap duoc cac UI bang port-forward.

### Observation gate

Theo doi trong 60 phut sau cutover:

- CloudFront 5xx error rate.
- CloudFront origin latency va origin errors.
- ALB healthy/unhealthy host count va target response time.
- Storefront synthetic smoke checks.

Rollback ngay neu:

- Xuat hien 502, 503 hoac 504 lien quan origin.
- 5xx vuot 1% trong 5 phut.
- Checkout hoac feature flags khong hoat dong.
- Internal ALB co unhealthy target.

## 8. Rollback

Truoc Phase E, rollback la mot Terraform apply dua primary CloudFront ve public origin
cu va tat continuous deployment policy. Neu WAF chan nham route runtime, disable rule
gay loi; chi disassociate WebACL sau khi continuous deployment policy da tat. Internal
ALB va VPC Origin duoc giu lai de dieu tra; khong xoa trong cung lenh rollback.

Sau khi rollback:

1. Xac minh storefront qua CloudFront tra 200.
2. Xac minh cart, checkout va feature flags.
3. Xac minh public origin targets healthy.
4. Ghi lai plan, apply run URL va runtime evidence.

Khong xoa public ALB cho toi khi observation gate dat va steady-state da nam tren `main`.

## 9. CI/CD va auditability

- Terraform plan/apply tiep tuc chi chay tren nhanh
  `deploy/account-migration-gitops` trong giai doan thu nghiem hien tai.
- Moi phase la mot saved plan rieng; apply dung dung artifact va checksum da review.
- Phase transition la manual approval; khong gop bootstrap, cutover va cleanup vao mot
  apply.
- Luu GitHub Actions run URL, Terraform plan summary, ALB target health, CloudFront/VPC
  Origin status va smoke-test output lam deployment evidence.
- Thay doi steady-state phai merge qua PR vao `main` truoc cleanup.

## 10. Chi phi va gioi han

- Trong migration se ton tai tam thoi hai ALB va mot staging distribution.
- AWS WAF la chi phi duy tri sau migration.
- CloudFront VPC Origin khong ho tro gRPC. Luong hien tai tu CloudFront toi Envoy dung
  HTTP/80; khong thay doi backend gRPC noi bo trong EKS.
- VPC Origin co the mat khoang 15 phut de dat `Deployed`; timeout nay khong duoc coi la
  loi neu AWS van dang provisioning.

## 11. Tai lieu tham chieu

- AWS CloudFront VPC origins:
  https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-vpc-origins.html
- AWS CloudFront continuous deployment:
  https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/continuous-deployment.html
- AWS CloudFront staging behavior:
  https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/understanding-continuous-deployment.html
- AWS Load Balancer Controller Ingress annotations:
  https://kubernetes-sigs.github.io/aws-load-balancer-controller/latest/guide/ingress/annotations/
- AWS WAF string match rules:
  https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-type-string-match.html
