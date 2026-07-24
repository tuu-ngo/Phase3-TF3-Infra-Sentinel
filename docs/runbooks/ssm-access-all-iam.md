# SSM Access — EKS API + RDS + ElastiCache (cho MỌI IAM)

Runbook chung cho **bất kỳ identity IAM nào** có quyền `ssm:StartSession` trên bastion,
không chỉ readonly. Dùng để mở SSM port-forward qua bastion tới:

- **EKS private API** (443) → `kubectl`
- **RDS PostgreSQL** (5432) → `psql`
- **ElastiCache Valkey** (6379) → `redis-cli`

> Runbook readonly (assume-role `tf3-production-readonly`) vẫn dùng được — xem
> [`member-readonly-ssm-access.md`](member-readonly-ssm-access.md) cho phần cấu hình profile readonly.
> Runbook này bổ sung: dùng cho **admin/operator IAM** và thêm đường tunnel **RDS/ElastiCache**.

---

## 0. Ai dùng được — identity nào cũng được, miễn có quyền SSM

| Nhóm | Cách xác thực | Quyền |
|---|---|---|
| Admin team (`AIO02`/`CDO01`/`CDO02`/`arthur`), `mentor` | Dùng profile riêng, ví dụ `export AWS_PROFILE=techx-new` (hoặc profile IAM của bạn ở account `197826770971`) | `AdministratorAccess` → đủ `ssm:StartSession` |
| Operator (`tf3-production-operator`) | Assume-role qua profile operator (xem [production-access-onboarding.md](production-access-onboarding.md)) | `ssm:StartSession` được cấp |
| Member readonly (`tf3-production-readonly`) | Theo [member-readonly-ssm-access.md](member-readonly-ssm-access.md) | `ssm:StartSession` được cấp |

Xác nhận identity trước khi làm:

```bash
aws sts get-caller-identity
```

Miễn ra `Account = 197826770971` và identity của bạn có `ssm:StartSession`, các bước dưới chạy được.

## 1. Chuẩn bị (một lần)

- AWS CLI v2: `aws --version`
- Session Manager Plugin: `session-manager-plugin --version` (thiếu thì cài theo tài liệu AWS)
- Client tuỳ mục tiêu: `kubectl` (EKS), `psql` (RDS), `redis-cli` (ElastiCache)

## 2. Tra bastion ID động (KHÔNG hardcode)

Bastion bị Terraform replace là đổi instance ID (đã xảy ra 23/07/2026 — xem postmortem 0013).
Luôn tra động theo tag:

```bash
export MSYS_NO_PATHCONV=1   # chỉ Windows git-bash
BASTION_ID=$(aws ec2 describe-instances --region ap-southeast-1 \
  --filters "Name=tag:Name,Values=techx-corp-tf3-bastion" \
            "Name=instance-state-name,Values=running" \
  --query "Reservations[].Instances[].InstanceId" --output text)
echo "bastion=$BASTION_ID"   # phải có giá trị, không rỗng
```

---

## 3. Tunnel EKS API → kubectl

```bash
EKS_HOST=$(aws eks describe-cluster --name techx-corp-tf3 --region ap-southeast-1 \
  --query "cluster.endpoint" --output text | sed 's~^https://~~')

# Terminal 1 — giữ chạy
aws ssm start-session --target "$BASTION_ID" \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters host="$EKS_HOST",portNumber="443",localPortNumber="8443" \
  --region ap-southeast-1
```

```bash
# Terminal 2
aws eks update-kubeconfig --name techx-corp-tf3 --region ap-southeast-1
kubectl config set-cluster arn:aws:eks:ap-southeast-1:197826770971:cluster/techx-corp-tf3 \
  --server=https://localhost:8443 --insecure-skip-tls-verify=true
kubectl get pods -n techx-tf3
```

---

## 4. Tunnel RDS PostgreSQL → psql

> **Yêu cầu hạ tầng:** bastion SG phải cho egress 5432. PM-126 từng siết egress về 443+DNS làm
> đường này timeout; đã khôi phục egress 5432 (scoped VPC CIDR) — xem postmortem 0014. Nếu vẫn
> timeout, kiểm mục Troubleshooting.

```bash
# Resolve endpoint động (hoặc dùng giá trị đã biết bên dưới)
RDS_HOST=$(aws rds describe-db-instances --region ap-southeast-1 \
  --db-instance-identifier techx-tf3-postgres \
  --query "DBInstances[0].Endpoint.Address" --output text)
# vd: techx-tf3-postgres.czwcs2ocww3q.ap-southeast-1.rds.amazonaws.com

# Terminal 1 — giữ chạy
aws ssm start-session --target "$BASTION_ID" \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters host="$RDS_HOST",portNumber="5432",localPortNumber="5432" \
  --region ap-southeast-1
```

```bash
# Terminal 2 — lấy credential từ Secrets Manager, KHÔNG hardcode mật khẩu
#   RDS dùng managed master password; app creds ở secret techx-tf3-postgres-conn.
aws secretsmanager list-secrets --region ap-southeast-1 \
  --query "SecretList[?contains(Name,'postgres')].Name" --output text

# vd đọc DSN app (thay tên secret cho đúng):
aws secretsmanager get-secret-value --region ap-southeast-1 \
  --secret-id techx-tf3-postgres-conn --query SecretString --output text

# Nối qua tunnel local:
psql "host=localhost port=5432 dbname=<db> user=<user> sslmode=require"
```

---

## 5. Tunnel ElastiCache Valkey → redis-cli

> **Yêu cầu hạ tầng:** bastion SG cho egress 6379 (đã khôi phục cùng bản vá RDS). ElastiCache bật
> TLS + auth token.

```bash
REDIS_HOST=$(aws elasticache describe-replication-groups --region ap-southeast-1 \
  --replication-group-id techx-tf3-valkey \
  --query "ReplicationGroups[0].NodeGroups[0].PrimaryEndpoint.Address" --output text)
# vd: master.techx-tf3-valkey.pkeslh.apse1.cache.amazonaws.com

# Terminal 1 — giữ chạy
aws ssm start-session --target "$BASTION_ID" \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters host="$REDIS_HOST",portNumber="6379",localPortNumber="6379" \
  --region ap-southeast-1
```

```bash
# Terminal 2 — auth token ở Secrets Manager (secret techx-tf3-valkey-auth)
AUTH=$(aws secretsmanager get-secret-value --region ap-southeast-1 \
  --secret-id techx-tf3-valkey-auth --query SecretString --output text)
redis-cli -h localhost -p 6379 --tls --insecure -a "$AUTH" PING   # -> PONG
```

---

## 6. Lỗi hay gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `TargetNotConnected` / `InvalidInstanceId` khi `start-session` | Đang trỏ bastion ID cũ đã terminate (Terraform replace) | Chạy lại mục 2 để lấy ID mới; **đừng hardcode ID** |
| `$BASTION_ID` rỗng | Chưa có bastion running, hoặc thiếu `ec2:DescribeInstances` | Kiểm EC2 console; nếu vẫn rỗng báo CDO |
| `AccessDeniedException` với `ssm:StartSession` | Identity không có quyền SSM | `aws sts get-caller-identity` xem đúng profile chưa; admin dùng `AWS_PROFILE=techx-new` |
| **`psql`/`redis-cli` timeout dù tunnel "opened"** | **Bastion SG egress chưa mở 5432/6379** (hệ quả PM-126) | Cần bản vá egress (postmortem 0014). Kiểm: `aws ec2 describe-security-groups --filters Name=tag:Name,Values=techx-corp-tf3-bastion-sg --query "SecurityGroups[0].IpPermissionsEgress[].FromPort"` phải có 5432/6379 |
| `connection refused localhost:<port>` | Tunnel chưa mở / đã đóng | Mở lại `start-session` ở Terminal 1, giữ chạy |
| `SessionManagerPlugin is not found` | Chưa cài plugin | Cài Session Manager Plugin rồi thử lại |

## 7. Audit

CloudTrail ghi mỗi SSM session theo identity gọi `StartSession`. Với admin dùng profile chung,
audit theo IAM user/role của profile đó. Muốn audit mạnh hơn: mỗi người một IAM/SSO riêng rồi
assume-role, session name mang tên người.
