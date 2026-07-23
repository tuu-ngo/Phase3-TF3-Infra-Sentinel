# Truy cập riêng tư Grafana, Jaeger và ArgoCD cho mentor

Runbook này dùng để mentor tự xác minh Mandate #1. Storefront vẫn công khai qua CloudFront;
các UI vận hành chỉ đi qua SSM bastion và Kubernetes port-forward.

## Link công khai (storefront)

Mentor mở trực tiếp trên trình duyệt, **không cần credential**:

**https://d2tn71186d7ilz.cloudfront.net**

Đây là cổng khách **duy nhất** được phép công khai. Mọi UI vận hành bên dưới phải KHÔNG truy cập
được qua internet công khai — xác minh ở mục 5 trên chính domain này: storefront `/` trả `200`,
còn `/grafana/`, `/jaeger/`, `/loadgen/`, `/feature/` trả `403`.

## Phạm vi quyền

- IAM user bootstrap: `mentor-mandate-reviewer`
- IAM role sử dụng khi kiểm tra: `arn:aws:iam::197826770971:role/techx-tf3-mandate-reviewer`
- Thời hạn mỗi role session: tối đa 1 giờ
- Kubernetes: chỉ đọc pod/service/log và port-forward trong `techx-tf3`, `argocd`
- Không được đọc Secret, sửa Deployment/Service/Ingress, đọc ArgoCD Application CR hoặc quản trị AWS

Tài khoản bootstrap và access key là tạm thời. Xóa ngay sau khi mentor xác nhận kết quả.

## 1. Bàn giao credential ngoài Git

Credential bootstrap đang được lưu trong AWS CLI profile cục bộ `mentor-mandate-bootstrap` trên máy
người tạo. Người quản trị lấy hai giá trị dưới đây và gửi cho mentor qua kênh bảo mật; không dán vào
issue, chat công khai, log CI hoặc file trong repo:

```sh
aws configure get aws_access_key_id --profile mentor-mandate-bootstrap
aws configure get aws_secret_access_key --profile mentor-mandate-bootstrap
```

Mentor cấu hình profile nguồn:

```sh
aws configure --profile mentor-mandate-bootstrap
# Region: ap-southeast-1
# Output: json

aws configure set role_arn \
  arn:aws:iam::197826770971:role/techx-tf3-mandate-reviewer \
  --profile mentor-mandate-reviewer
aws configure set source_profile mentor-mandate-bootstrap \
  --profile mentor-mandate-reviewer
aws configure set role_session_name mandate-01-review \
  --profile mentor-mandate-reviewer
aws configure set region ap-southeast-1 \
  --profile mentor-mandate-reviewer
```

Xác nhận role, không tiếp tục nếu ARN không đúng:

```sh
aws sts get-caller-identity --profile mentor-mandate-reviewer
```

ARN phải có dạng:

```text
arn:aws:sts::197826770971:assumed-role/techx-tf3-mandate-reviewer/mandate-01-review
```

## 2. Mở tunnel tới EKS private API

Terminal 1, giữ chạy trong suốt phiên kiểm tra.

> **Đừng hardcode instance ID bastion** — Terraform có thể replace bastion, ID sẽ
> đổi và lệnh trỏ ID cũ báo `TargetNotConnected` (đã xảy ra 23/07/2026). Tra ID
> động theo tag:

```sh
BASTION_ID=$(aws ec2 describe-instances --region ap-southeast-1 \
  --filters "Name=tag:Name,Values=techx-corp-tf3-bastion" \
            "Name=instance-state-name,Values=running" \
  --query "Reservations[].Instances[].InstanceId" --output text \
  --profile mentor-mandate-reviewer)

aws ssm start-session \
  --target "$BASTION_ID" \
  --document-name TechX-Mandate01-EKS-PortForward \
  --parameters localPortNumber="9443" \
  --region ap-southeast-1 \
  --profile mentor-mandate-reviewer
```

Custom document khóa đích tới EKS production API port `443`. Policy chỉ cho phép document này tới đúng
bastion; mentor không thể đổi remote host/port và không có quyền mở shell SSM.

## 3. Tạo kubeconfig riêng

Terminal 2:

```sh
export KUBECONFIG="$HOME/.kube/techx-mentor-mandate-01"

aws eks update-kubeconfig \
  --name techx-corp-tf3 \
  --region ap-southeast-1 \
  --profile mentor-mandate-reviewer \
  --kubeconfig "$KUBECONFIG"

CLUSTER=$(kubectl config view --minify -o jsonpath='{.contexts[0].context.cluster}')
kubectl config set-cluster "$CLUSTER" \
  --server=https://localhost:9443 \
  --insecure-skip-tls-verify=true

kubectl get pods -n techx-tf3
kubectl get services -n techx-tf3
kubectl get services -n argocd
```

TLS verification bị bỏ qua chỉ trên kết nối `localhost`; traffic tới EKS vẫn nằm trong tunnel SSM
được mã hóa. File kubeconfig này tách riêng để không ghi đè context làm việc khác của mentor.

## 4. Mở từng UI

Mỗi lệnh cần một terminal riêng và phải giữ chạy:

```sh
# Grafana: http://localhost:3000
KUBECONFIG="$HOME/.kube/techx-mentor-mandate-01" \
  kubectl -n techx-tf3 port-forward svc/grafana 3000:80

# Jaeger: http://localhost:16686/jaeger/ui/
KUBECONFIG="$HOME/.kube/techx-mentor-mandate-01" \
  kubectl -n techx-tf3 port-forward svc/jaeger 16686:16686

# ArgoCD: https://localhost:18443
KUBECONFIG="$HOME/.kube/techx-mentor-mandate-01" \
  kubectl -n argocd port-forward svc/argocd-server 18443:443
```

Port-forward chỉ mở trên loopback của máy mentor. Nó không tạo Ingress, LoadBalancer hoặc cổng public.

## 5. Checklist nghiệm thu

```sh
curl -I https://d2tn71186d7ilz.cloudfront.net/
curl -I https://d2tn71186d7ilz.cloudfront.net/grafana/
curl -I https://d2tn71186d7ilz.cloudfront.net/jaeger/
curl -I https://d2tn71186d7ilz.cloudfront.net/loadgen/
curl -I https://d2tn71186d7ilz.cloudfront.net/feature/

curl http://localhost:3000/api/health
curl http://localhost:16686/jaeger/ui/api/services
curl -k https://localhost:18443/api/version
```

Kết quả mong đợi: storefront `200`; bốn path vận hành public `403`; ba endpoint private `200`.

## 6. Thu hồi sau nghiệm thu

Chạy bằng profile quản trị, không chạy bằng profile mentor:

```sh
for key_id in $(aws iam list-access-keys \
  --user-name mentor-mandate-reviewer \
  --query 'AccessKeyMetadata[].AccessKeyId' \
  --output text); do
  aws iam delete-access-key \
    --user-name mentor-mandate-reviewer \
    --access-key-id "$key_id"
done

aws eks delete-access-entry \
  --cluster-name techx-corp-tf3 \
  --principal-arn arn:aws:iam::197826770971:role/techx-tf3-mandate-reviewer \
  --region ap-southeast-1

for namespace in techx-tf3 argocd; do
  kubectl -n "$namespace" delete rolebinding \
    mentor-mandate-observer mentor-mandate-port-forward
  kubectl -n "$namespace" delete role \
    mentor-mandate-observer mentor-mandate-port-forward
done

aws iam delete-role-policy \
  --role-name techx-tf3-mandate-reviewer \
  --policy-name MandateReviewerPrivateAccess
aws ssm delete-document \
  --name TechX-Mandate01-EKS-PortForward \
  --region ap-southeast-1
aws iam delete-user-policy \
  --user-name mentor-mandate-reviewer \
  --policy-name AssumeMandateReviewerRoleOnly
aws iam delete-role --role-name techx-tf3-mandate-reviewer
aws iam delete-user --user-name mentor-mandate-reviewer
```

Thu hồi các tài nguyên này không tác động storefront, workload, dữ liệu, flagd hoặc fault injection.
