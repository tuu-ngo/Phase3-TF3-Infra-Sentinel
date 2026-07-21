# Member Readonly SSM Access

Huong dan nay danh cho member dung IAM user `tf3-members-readonly` de truy cap
EKS private API qua SSM bastion. Member khong goi SSM truc tiep bang IAM user;
AWS CLI default profile se tu assume role `tf3-production-readonly`.

## Ket qua mong muon

Sau khi setup, lenh sau:

```bash
aws sts get-caller-identity
```

phai ra ARN dang:

```text
arn:aws:sts::197826770971:assumed-role/tf3-production-readonly/<ten>-readonly
```

CloudTrail se ghi SSM session theo `<ten>-readonly`.

## Chuan bi

1. Cai AWS CLI v2:

```bash
aws --version
```

2. Cai Session Manager Plugin:

```bash
session-manager-plugin --version
```

Neu chua co plugin, cai theo tai lieu AWS Session Manager Plugin cho he dieu
hanh dang dung.

3. Dung access key cua IAM user `tf3-members-readonly`.

## Setup lan dau

Chay `aws configure` va nhap access key/secret cua IAM user
`tf3-members-readonly`:

```bash
aws configure
```

Nhap:

```text
AWS Access Key ID: <access-key-cua-tf3-members-readonly>
AWS Secret Access Key: <secret-key-cua-tf3-members-readonly>
Default region name: ap-southeast-1
Default output format: json
```

Sau do chay script setup profile. Ten bat buoc phai ket thuc bang
`-readonly`:

```bash
scripts/setup-readonly-aws-profile.sh <ten>-readonly
```

Vi du:

```bash
scripts/setup-readonly-aws-profile.sh tu-readonly
```

Script se:

- backup `~/.aws/credentials` va `~/.aws/config`;
- chuyen credential IAM user sang profile `tf3-member-base`;
- cau hinh `[default]` tu assume role `tf3-production-readonly`;
- chan session name khong ket thuc bang `-readonly`.

## Verify identity

Chay:

```bash
aws sts get-caller-identity
```

Dung khi thay:

```text
arn:aws:sts::197826770971:assumed-role/tf3-production-readonly/<ten>-readonly
```

Sai neu van thay:

```text
arn:aws:iam::197826770971:user/tf3-members-readonly
```

Neu sai, chay lai:

```bash
scripts/setup-readonly-aws-profile.sh <ten>-readonly
```

## Mo SSM tunnel

Mo terminal rieng va giu terminal nay chay:

```bash
aws ssm start-session \
  --target i-02a8d3e39b87180ce \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters host="ADA05FFC84146C0AED730F78786EB320.gr7.ap-southeast-1.eks.amazonaws.com",portNumber="443",localPortNumber="8443" \
  --region ap-southeast-1
```

Thanh cong khi thay:

```text
Starting session with SessionId: <ten>-readonly-...
Port 8443 opened for sessionId ...
Waiting for connections...
```

Dung xong bam `Ctrl+C` de dong tunnel.

## Cau hinh kubectl

Mo terminal khac, trong khi SSM tunnel o tren van dang chay:

```bash
aws eks update-kubeconfig --name techx-corp-tf3 --region ap-southeast-1

kubectl config set-cluster arn:aws:eks:ap-southeast-1:197826770971:cluster/techx-corp-tf3 \
  --server=https://localhost:8443 \
  --insecure-skip-tls-verify=true
```

Kiem tra:

```bash
kubectl get pods -n techx-tf3
kubectl auth can-i get pods -n techx-tf3
kubectl auth can-i patch deployments -n techx-tf3
kubectl auth can-i create pods/portforward -n techx-tf3
kubectl auth can-i create pods/portforward -n argocd
```

Readonly dung ky vong:

```text
yes
yes
no
yes
yes
```

## Mo UI observability

Moi lenh port-forward can mot terminal rieng va phai giu terminal do chay.
SSM tunnel toi EKS API o tren van phai dang mo.

```bash
# Grafana: http://localhost:3000
kubectl -n techx-tf3 port-forward svc/grafana 3000:80

# Jaeger: http://localhost:16686/jaeger/ui/
kubectl -n techx-tf3 port-forward svc/jaeger 16686:16686

# ArgoCD: https://localhost:18443
kubectl -n argocd port-forward svc/argocd-server 18443:443
```

Port-forward chi mo tren loopback cua may member. No khong tao Ingress,
LoadBalancer, NodePort, hay cong public.

## Loi hay gap

| Loi | Nguyen nhan | Cach xu ly |
| --- | --- | --- |
| `AccessDeniedException` voi `ssm:StartSession` | Dang chay bang IAM user goc, chua assume role | Chay `aws sts get-caller-identity`; neu ra `user/tf3-members-readonly`, chay lai script setup |
| `SessionManagerPlugin is not found` | May chua cai Session Manager Plugin | Cai plugin roi chay lai |
| `connection refused localhost:8443` | SSM tunnel chua mo hoac da dong | Mo lai lenh `aws ssm start-session` va giu terminal do |
| `x509 ... not localhost` | Kubeconfig chua set localhost tunnel | Chay lai lenh `kubectl config set-cluster` o tren |

## Audit

CloudTrail se ghi hai lop:

- `tf3-members-readonly` goi `AssumeRole`;
- `assumed-role/tf3-production-readonly/<ten>-readonly` goi `StartSession`.

Voi shared IAM user, `<ten>-readonly` la audit theo session name. Audit manh hon
can moi member co IAM user rieng hoac SSO identity rieng, sau do cung assume
role readonly.
