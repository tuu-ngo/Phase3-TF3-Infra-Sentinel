# Runbook - Mandate 18: hidden cost cleanup evidence ngoài node compute

Runbook này dùng để chuẩn bị evidence cho Mandate 18: chứng minh TF3/CDO đã kiểm tra và cắt chi phí ẩn ngoài phần EKS node compute, nhưng vẫn giữ SLO và khả năng vận hành/điều tra.

Mandate 18 không thay thế Mandate 13. Mandate 13 xử lý compute node-hours bằng Spot/Karpenter/Graviton. Runbook này cố ý loại `Amazon Elastic Compute Cloud - Compute` khỏi phần claim chính và tập trung vào:

- orphan resources: EBS, EIP, snapshot/AMI, load balancer, target group
- storage lifecycle/type/right-size
- NAT/VPC endpoint/data transfer
- telemetry retention/ingestion/cardinality
- top non-compute cost drivers

## 1. Nguyên tắc an toàn

Không chạy cleanup nếu chưa có đủ owner và approval.

Không dùng runbook này để:

- xóa EBS volume nếu chưa đối chiếu PV/PVC và workload live;
- xóa hoặc sửa S3 bucket không rõ owner;
- đặt lifecycle xóa current object của Terraform state;
- tắt EKS audit log chỉ để giảm bill;
- đổi NAT/VPC endpoint nếu chưa hiểu ảnh hưởng tới private ECR pull, SSM tunnel, Secrets Manager, STS hoặc luồng vận hành;
- claim saving bằng bill `$` ròng trong account đang có credit.

Evidence chính phải là usage:

- EBS: GiB-month
- NAT: NAT gateway-hour, NAT data processing GB
- VPC endpoint: endpoint-hour, processed bytes nếu có
- S3: storage class, object count/bytes, lifecycle rule
- CloudWatch: stored bytes, ingestion volume nếu có
- orphan cleanup: số resource và dung lượng/giờ tài nguyên đã giảm

## 2. Coordination gate với Mandate 13 và SLO

CDO02 chịu cả Cost Optimization và Reliability, nên Mandate 18 không được làm theo kiểu "cắt được tiền nhưng làm hỏng SLO". Nếu Mandate 13 đang chạy load test, scale-out/scale-down hoặc spot interruption demo, evidence và thao tác Mandate 18 phải được tách riêng để không gạt chân nhau.

### 2.1. Nguyên tắc tách cửa sổ

Không chạy cleanup/optimization có khả năng ảnh hưởng runtime trong các cửa sổ sau:

- 60 phút trước Mandate 13 load test hoặc spot interruption demo;
- trong lúc Mandate 13 đang tạo tải, drain node, hoặc quay video;
- 60 phút sau demo, trừ khi team đã xác nhận SLO ổn định trở lại.

Nếu chỉ chạy read-only inventory cho Mandate 18 thì có thể làm song song, nhưng evidence phải ghi rõ timestamp để tránh lẫn với spike do Mandate 13.

### 2.2. Action Mandate 18 nào có thể làm song song với Mandate 13?

| Action Mandate 18 | Có thể làm song song với Mandate 13? | Điều kiện |
|---|---|---|
| Read-only inventory EBS/EIP/LB/TG/S3/CloudWatch | Có | Ghi timestamp và không claim cost trend từ cửa sổ đang load test |
| Verify EBS `available` bằng AWS CLI | Có | Chỉ đọc, chưa delete |
| Verify PV/PVC bằng `kubectl get` | Có | Chỉ đọc, không patch/delete |
| Delete EBS orphan đã verify | Không nên trong cửa sổ demo 13 | Chạy ngoài cửa sổ 13, theo dõi SLO/events sau cleanup |
| S3 lifecycle change | Không nên nếu bucket liên quan audit/ops | Cần owner, không đụng tfstate current object |
| NAT/VPC endpoint change | Không | Có thể làm mất ECR pull, SSM tunnel, private ops path |
| CloudWatch/audit log change | Không | Có thể làm mù điều tra Mandate 11/12 và incident response |
| Telemetry sampling/cardinality change | Không trong lúc 13 demo | Dễ làm mất khả năng chứng minh SLO của 13 |

### 2.3. Các loại nhiễu giữa 13 và 18

| Nhiễu | Vì sao nguy hiểm | Cách xử lý |
|---|---|---|
| Load test 13 làm tăng log/trace/metric | Mandate 18 có thể bị hỏi vì sao telemetry tăng | Không dùng cửa sổ 13 để claim telemetry reduction |
| Spot interruption làm pod reschedule/image pull | NAT/ECR endpoint traffic tăng tạm thời | Không kết luận NAT/endpoint cost từ cửa sổ demo |
| Karpenter scale node lên/xuống | EBS root volume/node inventory thay đổi | Chỉ xét EBS orphan `available` có tag PVC/PV cũ |
| SLO spike do 13 | Không biết spike do 13 hay do cleanup 18 | Không chạy cleanup 18 trong cùng cửa sổ |
| Cắt telemetry trong 18 | 13 mất bằng chứng Grafana/trace để pass | Giữ observability nguyên vẹn đến khi 13 xong |

### 2.4. SLO gate trước khi làm cleanup Mandate 18

Trước mọi cleanup/optimization có khả năng ảnh hưởng runtime, phải kiểm tra:

- không có Mandate 13 demo/load test đang mở;
- không có incident đang active;
- checkout success đang >= 99%;
- browse/cart success đang >= 99.5%;
- storefront p95 đang < 1s;
- Grafana/Prometheus/Jaeger vẫn quan sát được;
- `kubectl -n techx-tf3 get events --sort-by=.lastTimestamp` không có lỗi mới đáng ngại.

Nếu một trong các điều kiện trên không đạt, kết luận:

```text
NO-GO: postpone Mandate 18 cleanup because reliability/SLO window is not clean.
```

### 2.5. SLO evidence sau cleanup

Sau cleanup/optimization, phải có một cửa sổ quan sát riêng cho Mandate 18:

- tối thiểu 30 phút cho cleanup không ảnh hưởng data path, ví dụ xóa EBS orphan đã verify;
- 60 phút hoặc hơn nếu action chạm network/telemetry/route;
- không dùng cùng cửa sổ với Mandate 13 spot interruption để claim 18 pass.

Evidence tối thiểu:

- Grafana trước/sau action;
- `kubectl get pods/events` trước/sau;
- nếu action liên quan network, xác nhận SSM/kubectl tunnel, ECR pull path và private ops UI vẫn hoạt động;
- nếu action liên quan telemetry, xác nhận dashboard/trace/log vẫn đủ điều tra.

## 3. Điều kiện tiên quyết

Máy chạy cần có:

- AWS CLI đã dùng được với account `197826770971`;
- quyền read-only đủ để đọc EC2, ELBv2, S3, CloudWatch, Cost Explorer;
- `kubectl` nếu cần verify PV/PVC trong EKS;
- tunnel kubectl nếu EKS API private-only;
- Grafana/Prometheus nếu cần chụp SLO trước-sau.

Thiết lập biến môi trường PowerShell:

```powershell
$env:AWS_PROFILE = "<profile-197826770971>"
$env:AWS_REGION = "ap-southeast-1"
$ClusterName = "techx-corp-tf3"
$Namespace = "techx-tf3"
```

Kiểm tra identity trước khi lấy evidence:

```powershell
aws sts get-caller-identity --profile $env:AWS_PROFILE
```

Expected:

- `Account` là `197826770971`;
- actor đúng credential được phép đọc;
- không dùng nhầm account lab/cá nhân.

## 4. Deliverable phải nộp

Sau khi chạy runbook, evidence nên gom vào một file hoặc comment PR/Jira theo format:

```text
Mandate 18 - Hidden Cost Cleanup Evidence

Scope:
- Non-compute hidden cost only.
- EC2 node compute is handled by Mandate 13.

Before:
- Orphan resources inventory.
- Storage/lifecycle inventory.
- NAT/VPC endpoint inventory.
- Telemetry inventory.
- Top non-compute cost drivers.

Actions:
- What was cleaned or intentionally kept.
- Who approved.
- Exact timestamp.

After:
- Same commands/screenshots after action.
- Usage reduced.
- SLO/observability still healthy.

Residual risks:
- Items kept because they are required for operations.
- Items handed off to another owner.
```

## 5. Current cutdown snapshot

Snapshot này là baseline live đã kiểm tra bằng AWS CLI read-only trong account `197826770971`, region `ap-southeast-1`, ngày 2026-07-23. Trước khi cleanup thật, phải chạy lại các lệnh inventory ở phần sau vì hạ tầng thay đổi nhanh.

| Nhóm | Snapshot hiện tại | Cutdown candidate | Evidence để pass |
|---|---|---|---|
| EBS `available` | 3 volume `gp2`, tổng 6GiB, có tag PVC cũ `valkey-cart`, `kafka-data`, `postgresql-data` | Có, candidate rõ nhất | Verify không còn PV/PVC/workload live, approval owner, delete sau approval, after evidence volume not found |
| EIP unattached | Không thấy; EIP `13.213.127.91` đang gắn NAT | Không | Screenshot/CLI chứng minh EIP có `AssociationId` |
| Snapshot self-owned | 0 | Không | CLI count/output bằng 0 |
| AMI self-owned | 0 | Không | CLI count/output bằng 0 |
| ALB/TG orphan | 1 internal ALB `techx-tf3-frontend-internal`, 1 TG attached | Không thấy orphan | CLI chứng minh TG có attached ALB |
| NAT | 1 public NAT `nat-0b963ceaf95a7817f` | Không cleanup ngay | Decision record: NAT còn phục vụ private egress, chỉ tối ưu khi có route/endpoint analysis |
| VPC endpoints | S3 Gateway + 5 Interface endpoints x 3 subnets | Có thể là optimization candidate | Decision record endpoint-hour vs NAT data, không phá SSM/ECR/private access |
| S3 lifecycle | Audit trail 30 ngày, sosflow ALB logs 7 ngày, bucket khác cần owner | Có owner-matrix candidate | Bucket owner matrix, lifecycle hoặc lý do giữ lại |
| CloudWatch | EKS cluster log retention 90 ngày, stored ~4.38GB; audit Lambda 14 ngày | Không cắt mù audit | Decision record giữ audit log; nếu tối ưu phải nhắm ingestion/cardinality/sampling |

### 5.1. Candidate cutdown đang rõ nhất

Ba EBS volume sau là mũi có thể làm evidence nhanh nhất, vì chúng đang `available`, không attach instance nào, tổng 6GiB `gp2`:

| Volume | AZ | Type | Size | PVC tag | PV tag |
|---|---|---|---|---|---|
| `vol-05d59d76c58a9d835` | `ap-southeast-1a` | `gp2` | 1GiB | `valkey-cart` | `pvc-564c4984-9b3e-488d-8b0a-7db0806a2edd` |
| `vol-0a22f104910589929` | `ap-southeast-1b` | `gp2` | 3GiB | `kafka-data` | `pvc-3d2172ad-7068-4302-85e1-990195aafc9e` |
| `vol-0f4b0c53ef8091d52` | `ap-southeast-1a` | `gp2` | 2GiB | `postgresql-data` | `pvc-65777d66-5c41-4186-80b7-a0931167a634` |

Pass evidence tối thiểu cho mũi này:

1. Before CLI/console cho thấy 3 volume ở trạng thái `available`.
2. `kubectl get pv,pvc -A` và `kubectl -n techx-tf3 get pods -o wide` cho thấy không còn workload/PVC live phụ thuộc các PV/PVC tag đó.
3. Có approval owner để cleanup.
4. Sau cleanup, `describe-volumes --volume-ids ...` trả `InvalidVolume.NotFound` hoặc console không còn volume.
5. Grafana/SLO và kubectl events không có regression sau cleanup.

Nếu không có kubectl hoặc không verify được PV/PVC, không được xóa. Ghi `NO-GO` và để candidate ở trạng thái pending evidence.

### 5.2. Candidate lớn hơn nhưng cần decision, không cleanup vội

VPC Interface endpoints là mũi cost lớn hơn EBS nhưng rủi ro hơn. Snapshot hiện có 5 interface endpoints, mỗi endpoint gắn 3 subnet:

- ECR DKR
- ECR API
- SSM
- EC2 Messages
- SSM Messages

Theo cost breakdown hiện có, nhóm này ước tính khoảng `$32.8/tuần`. Tuy nhiên endpoint này có thể đang giữ cho ECR image pull và SSM/kubectl tunnel hoạt động trong private network. Vì vậy evidence pass ở đây không nhất thiết là xóa endpoint; pass tốt hơn là một decision record có số:

- NAT data processing hiện thấp hay cao?
- endpoint-hour đang tốn bao nhiêu?
- endpoint nào là bắt buộc cho vận hành private?
- nếu thu hẹp endpoint theo AZ hoặc bỏ endpoint, rollback thế nào?

Không tối ưu VPC endpoint bằng tay trong lúc chưa có rollout plan, vì lỗi có thể làm mất đường vận hành hoặc image pull.

### 5.3. Candidate không nên cắt bừa

CloudWatch EKS audit log đang là cost driver do ingestion, nhưng cũng là dữ liệu điều tra cho Mandate 11/12 và incident response. Không nên claim Mandate 18 bằng cách tắt audit log.

Pass evidence hợp lý:

- ghi rõ retention hiện tại: `/aws/eks/techx-corp-tf3/cluster` retention 90 ngày, stored khoảng 4.38GB;
- ghi rõ vì sao không tắt audit log;
- nếu muốn tối ưu telemetry, đề xuất nhắm vào nguồn ingestion/cardinality/sampling thay vì làm mù audit.

S3 bucket cũng không nên bị apply lifecycle chung. Bucket audit trail đã có lifecycle 30 ngày, `sosflow-alb-logs` có 7 ngày, bucket tfstate không được xóa current object. Các bucket AIO/SOSFlow/Tokyo phải phân owner trước.

## 6. Read-only inventory before action

### 6.1. EBS volumes

Liệt kê EBS volumes đang `available`:

```powershell
aws ec2 describe-volumes `
  --profile $env:AWS_PROFILE `
  --region $env:AWS_REGION `
  --filters Name=status,Values=available `
  --query "Volumes[].{VolumeId:VolumeId,State:State,Type:VolumeType,SizeGiB:Size,AZ:AvailabilityZone,CreateTime:CreateTime,Name:Tags[?Key=='Name']|[0].Value,PVC:Tags[?Key=='kubernetes.io/created-for/pvc/name']|[0].Value,Namespace:Tags[?Key=='kubernetes.io/created-for/pvc/namespace']|[0].Value,PV:Tags[?Key=='kubernetes.io/created-for/pv/name']|[0].Value}" `
  --output table
```

Evidence cần chụp:

- `VolumeId`
- trạng thái `available`
- `VolumeType`
- `SizeGiB`
- tag PVC/PV nếu có
- timestamp lệnh chạy

Known candidate tại snapshot 2026-07-23, cần verify lại trước khi xóa:

| Volume | State | Type | Size | Tag liên quan |
|---|---|---|---|---|
| `vol-05d59d76c58a9d835` | `available` | `gp2` | 1GiB | old `valkey-cart` PVC |
| `vol-0a22f104910589929` | `available` | `gp2` | 3GiB | old `kafka-data` PVC |
| `vol-0f4b0c53ef8091d52` | `available` | `gp2` | 2GiB | old `postgresql-data` PVC |

Tổng candidate: `6 GiB gp2 available`.

Giá gp2 `ap-southeast-1` tại thời điểm kiểm tra: `$0.12 / GB-month`.

Saving nếu confirmed orphan và cleanup:

```text
6 GiB x $0.12 = $0.72 / month
~$0.17 / week
```

Số tiền nhỏ, nhưng evidence đúng mandate vì giảm được `6 GiB-month` orphan storage.

### 6.2. Verify EBS candidate không còn PV/PVC live

Chỉ cần chạy nếu kubectl đang vào được cluster:

```powershell
kubectl get pv,pvc -A
kubectl -n $Namespace get pvc
kubectl -n $Namespace get pods -o wide
```

Nếu cần tra từng PV/PVC theo tag:

```powershell
kubectl get pv | Select-String "pvc-"
kubectl -n $Namespace get pvc | Select-String "valkey|kafka|postgres"
```

Điều kiện để mark EBS là orphan thật:

- volume `available`, không attach instance nào;
- PV/PVC tương ứng không còn tồn tại hoặc đã chuyển sang storage backend mới;
- không có pod live phụ thuộc PVC đó;
- owner xác nhận được phép cleanup.

Nếu thiếu một điều kiện, ghi:

```text
NO-GO: volume is not proven orphan yet.
```

### 6.3. EIP unattached

```powershell
aws ec2 describe-addresses `
  --profile $env:AWS_PROFILE `
  --region $env:AWS_REGION `
  --query "Addresses[].{PublicIp:PublicIp,AllocationId:AllocationId,AssociationId:AssociationId,NetworkInterfaceId:NetworkInterfaceId,InstanceId:InstanceId,Tags:Tags}" `
  --output table
```

Evidence pass:

- không có EIP nào thiếu `AssociationId`; hoặc
- EIP thiếu association đã được xác nhận owner và release sau approval.

Snapshot 2026-07-23:

```text
EIP 13.213.127.91 đang gắn với NAT Gateway
Không thấy EIP unattached
```

### 6.4. Snapshot và AMI self-owned

```powershell
aws ec2 describe-snapshots `
  --profile $env:AWS_PROFILE `
  --region $env:AWS_REGION `
  --owner-ids self `
  --query "Snapshots[].{SnapshotId:SnapshotId,VolumeSize:VolumeSize,StartTime:StartTime,Description:Description,StorageTier:StorageTier,State:State}" `
  --output table

aws ec2 describe-images `
  --profile $env:AWS_PROFILE `
  --region $env:AWS_REGION `
  --owners self `
  --query "Images[].{ImageId:ImageId,Name:Name,CreationDate:CreationDate,State:State,BlockDevices:BlockDeviceMappings[].Ebs.SnapshotId}" `
  --output table
```

Evidence pass:

- không có snapshot/AMI self-owned; hoặc
- có danh sách snapshot/AMI giữ lại kèm owner/lý do/lifecycle; hoặc
- snapshot/AMI rác đã cleanup sau approval.

Snapshot 2026-07-23: chưa thấy self-owned snapshot/AMI trong `ap-southeast-1`.

### 6.5. Load balancer và target group orphan

```powershell
aws elbv2 describe-load-balancers `
  --profile $env:AWS_PROFILE `
  --region $env:AWS_REGION `
  --query "LoadBalancers[].{Name:LoadBalancerName,Arn:LoadBalancerArn,Scheme:Scheme,Type:Type,State:State.Code,VpcId:VpcId,DNSName:DNSName}" `
  --output table

aws elbv2 describe-target-groups `
  --profile $env:AWS_PROFILE `
  --region $env:AWS_REGION `
  --query "TargetGroups[].{Name:TargetGroupName,Arn:TargetGroupArn,Protocol:Protocol,Port:Port,LoadBalancerArns:LoadBalancerArns}" `
  --output table
```

Với target group nghi ngờ, kiểm tra target health:

```powershell
$TargetGroupArn = "<target-group-arn>"
aws elbv2 describe-target-health `
  --profile $env:AWS_PROFILE `
  --region $env:AWS_REGION `
  --target-group-arn $TargetGroupArn `
  --output table
```

Evidence pass:

- mỗi LB đang có owner và route rõ;
- target group có attached LB hoặc có lý do giữ lại;
- target group không attached và không có target live phải được mark candidate cleanup.

Snapshot 2026-07-23:

```text
ALB: techx-tf3-frontend-internal, active, internal
Target group: k8s-techxtf3-frontend-a9095982ec, attached to ALB
Không thấy LB/TG orphan rõ ràng
```

### 6.6. NAT gateway và VPC endpoints

```powershell
aws ec2 describe-nat-gateways `
  --profile $env:AWS_PROFILE `
  --region $env:AWS_REGION `
  --query "NatGateways[].{NatGatewayId:NatGatewayId,State:State,VpcId:VpcId,SubnetId:SubnetId,ConnectivityType:ConnectivityType,PublicIp:NatGatewayAddresses[0].PublicIp}" `
  --output table

aws ec2 describe-vpc-endpoints `
  --profile $env:AWS_PROFILE `
  --region $env:AWS_REGION `
  --query "VpcEndpoints[].{VpcEndpointId:VpcEndpointId,Type:VpcEndpointType,ServiceName:ServiceName,State:State,VpcId:VpcId,Subnets:SubnetIds,PrivateDnsEnabled:PrivateDnsEnabled}" `
  --output table
```

Snapshot 2026-07-23:

```text
NAT: 1 NAT Gateway đang available
VPC endpoint:
- S3 Gateway endpoint
- ECR API interface endpoint
- ECR DKR interface endpoint
- SSM interface endpoint
- SSM Messages interface endpoint
- EC2 Messages interface endpoint
```

Theo `docs/cost-breakdown-2026-07-22.md`, VPC interface endpoints là cost driver đáng kể:

```text
5 interface endpoints x 3 AZ = 15 ENI
ước tính khoảng $32.8/tuần
```

Decision cần ghi rõ:

- giữ S3 Gateway endpoint vì nó phù hợp private S3 access và không tính hourly như interface endpoint;
- không mặc định thêm endpoint mới là tiết kiệm;
- với ECR/SSM interface endpoints, phải cân giữa chi phí endpoint-hour và nhu cầu private ECR pull/SSM tunnel;
- nếu thu hẹp endpoint hoặc NAT, phải có rollback plan và cửa sổ quan sát.

### 6.7. S3 lifecycle và owner matrix

Liệt kê bucket:

```powershell
aws s3api list-buckets `
  --profile $env:AWS_PROFILE `
  --query "Buckets[].{Name:Name,CreationDate:CreationDate}" `
  --output table
```

Kiểm tra lifecycle từng bucket:

```powershell
$Buckets = aws s3api list-buckets `
  --profile $env:AWS_PROFILE `
  --query "Buckets[].Name" `
  --output text

foreach ($Bucket in $Buckets.Split()) {
  Write-Host "=== $Bucket ==="
  aws s3api get-bucket-lifecycle-configuration `
    --profile $env:AWS_PROFILE `
    --bucket $Bucket 2>$null
}
```

Owner matrix cần có:

| Bucket | Owner | Lifecycle hiện tại | Có được đổi không? | Lý do |
|---|---|---|---|---|
| `techx-tf3-197826770971-tfstate` | TF3 infra | Không xóa current state | Không tự đổi nếu chưa approve | Terraform state |
| `techx-corp-tf3-audit-trail...` | CDO audit | 30 ngày | Cẩn thận | Mandate 11/12 evidence |
| `sosflow-*` | cần xác minh | tùy bucket | chưa rõ | có thể out-of-scope |
| `tf3-aiops-*` | AIO | cần xác minh | chưa rõ | owner khác |

Evidence pass:

- bucket owned by CDO/TF3 có lifecycle hợp lý; hoặc
- bucket không có lifecycle nhưng có lý do giữ; hoặc
- bucket out-of-scope được handoff owner.

Không đặt lifecycle xóa current object của Terraform state. Nếu cần giảm tfstate storage, chỉ cân nhắc noncurrent version lifecycle sau approval.

### 6.8. CloudWatch logs và telemetry

Liệt kê log group:

```powershell
aws logs describe-log-groups `
  --profile $env:AWS_PROFILE `
  --region $env:AWS_REGION `
  --query "logGroups[].{Name:logGroupName,Retention:retentionInDays,StoredBytes:storedBytes,Created:creationTime}" `
  --output table
```

Snapshot 2026-07-23:

```text
/aws/eks/techx-corp-tf3/cluster
- retention: 90 days
- stored bytes: khoảng 4.38GB

/aws/lambda/techx-corp-tf3-audit-detection-ap-southeast-1-router
- retention: 14 days
- nhỏ

/aws/lambda/tf2-finops-ai-test
- retention: null
- rất nhỏ, có vẻ old/out-of-scope candidate
```

Decision quan trọng:

- không claim hạ retention CloudWatch là saving lớn nếu ingestion vẫn giữ nguyên;
- không tắt EKS audit log nếu nó đang phục vụ Mandate 11/12 và incident investigation;
- nếu muốn giảm telemetry cost, tìm nguồn ingestion/cardinality/sampling trước, không cắt mù observability.

Evidence pass:

- mỗi log group quan trọng có retention hữu hạn;
- log group vô hạn retention có owner hoặc được xử lý;
- audit log được giữ có lý do rõ;
- Grafana/Jaeger/CloudTrail vẫn đủ điều tra incident sau tối ưu.

### 6.9. Top non-compute cost drivers

Cost Explorer chỉ để tham khảo vì account có credit. Dùng usage/cost breakdown chưa trừ credit nếu có.

Lệnh xem service cost 7 ngày gần nhất:

```powershell
$Start = (Get-Date).AddDays(-7).ToString("yyyy-MM-dd")
$End = (Get-Date).ToString("yyyy-MM-dd")

aws ce get-cost-and-usage `
  --profile $env:AWS_PROFILE `
  --time-period Start=$Start,End=$End `
  --granularity DAILY `
  --metrics UnblendedCost UsageQuantity `
  --group-by Type=DIMENSION,Key=SERVICE `
  --output json
```

Các nguồn đã có trong `docs/cost-breakdown-2026-07-22.md`:

- MSK là cost driver lớn, nhưng cần phân owner/mandate vì có thể gắn Mandate 8/Kafka;
- EC2 node compute thuộc Mandate 13, không claim cho 18;
- VPC endpoints là hidden network cost đáng chú ý;
- CloudWatch EKS logs tốn do ingestion, không phải do retention storage;
- AOSS/AI hoặc stack ngoài Phase 3 cần owner trước khi cleanup.

## 7. Action gate trước khi cleanup hoặc optimize

Trước khi chạy bất kỳ lệnh thay đổi nào, phải có:

- owner tài nguyên;
- ticket hoặc PR/comment approve;
- before evidence đã chụp;
- rollback hoặc lý do không cần rollback;
- cửa sổ theo dõi SLO nếu có khả năng ảnh hưởng runtime.

Các lệnh dưới đây là ví dụ để owner chạy sau approval, không chạy trong bước inventory.

### 7.1. Delete EBS orphan sau approval

```powershell
# Chỉ chạy sau khi PV/PVC/workload đã verify không còn dùng.
$VolumeId = "<confirmed-orphan-volume-id>"

aws ec2 delete-volume `
  --profile $env:AWS_PROFILE `
  --region $env:AWS_REGION `
  --volume-id $VolumeId
```

After evidence:

```powershell
aws ec2 describe-volumes `
  --profile $env:AWS_PROFILE `
  --region $env:AWS_REGION `
  --volume-ids $VolumeId
```

Expected:

- volume không còn tồn tại; hoặc
- API trả `InvalidVolume.NotFound`.

### 7.2. Release EIP unattached sau approval

```powershell
# Chỉ chạy nếu EIP không có AssociationId và owner xác nhận cleanup.
$AllocationId = "<allocation-id>"

aws ec2 release-address `
  --profile $env:AWS_PROFILE `
  --region $env:AWS_REGION `
  --allocation-id $AllocationId
```

### 7.3. Lifecycle S3 sau approval

Không áp dụng chung cho mọi bucket. Mỗi bucket cần lifecycle riêng theo owner.

Ví dụ chỉ minh họa:

```json
{
  "Rules": [
    {
      "ID": "expire-noncurrent-versions-after-30-days",
      "Status": "Enabled",
      "Filter": {},
      "NoncurrentVersionExpiration": {
        "NoncurrentDays": 30
      }
    }
  ]
}
```

Không dùng rule này để xóa current Terraform state.

## 8. SLO và vận hành sau cleanup

Sau cleanup/optimization, theo dõi ít nhất 30-60 phút nếu action có thể ảnh hưởng runtime hoặc đường vận hành.

Chụp:

```powershell
kubectl -n $Namespace get pods -o wide
kubectl -n $Namespace get events --sort-by=.lastTimestamp
kubectl get nodes -o wide
```

Dashboard cần kiểm:

- storefront p95;
- browse/cart success rate;
- checkout success rate;
- Grafana/Prometheus vẫn scrape;
- Jaeger/trace vẫn xem được nếu có;
- SSM/kubectl tunnel vẫn còn đường vào nếu endpoint/NAT bị chỉnh.

Nếu SLO tụt hoặc mất observability, rollback hoặc mở incident. Không claim Mandate 18 done khi hệ thống bị mù vận hành.

## 9. Checklist evidence done

Mandate 18 có thể coi là có evidence tốt khi có đủ:

- [ ] scope ghi rõ: non-compute hidden cost, không đếm trùng Mandate 13;
- [ ] before inventory EBS/EIP/snapshot/AMI/LB/TG có timestamp;
- [ ] before inventory NAT/VPC endpoint có timestamp;
- [ ] before inventory S3 lifecycle và owner matrix có timestamp;
- [ ] before inventory CloudWatch/telemetry retention có timestamp;
- [ ] top non-compute cost-driver được chỉ ra bằng usage/cost breakdown;
- [ ] với EBS candidate: đã verify PV/PVC/workload live trước khi delete;
- [ ] với NAT/VPC endpoint: có decision record endpoint-hour vs NAT data, không làm mất private access;
- [ ] với S3: bucket có owner, không đụng tfstate current object, audit trail có lý do retention;
- [ ] với CloudWatch: giữ auditability hoặc có kế hoạch giảm ingestion không làm mù hệ thống;
- [ ] ít nhất một cleanup/optimization thật hoặc decision record giữ lại có lý do;
- [ ] after inventory chứng minh resource/usage đã giảm hoặc lý do không cleanup;
- [ ] SLO/observability sau action vẫn ổn;
- [ ] residual risk và owner handoff được ghi rõ.

### 9.1. Checklist pass theo từng nhóm tài nguyên

| Nhóm | Pass khi nào? | Fail khi nào? |
|---|---|---|
| EBS orphan | Không còn volume `available` không owner, hoặc còn nhưng có ticket/NO-GO rõ | Xóa volume khi chưa verify PV/PVC; còn volume orphan nhưng không giải thích |
| EIP | Không có EIP unattached, hoặc đã release sau approval | Có EIP unattached tính tiền mà không owner |
| Snapshot/AMI | Không có snapshot/AMI rác, hoặc có lifecycle/owner | Snapshot/AMI giữ vô hạn không owner |
| LB/TG | Không có LB/TG orphan, TG đều attached hoặc có lý do | TG/LB không dùng vẫn tính tiền |
| NAT/VPC endpoint | Có analysis usage và decision giữ/cắt rõ | Cắt endpoint/NAT làm mất private ops hoặc không có số liệu |
| S3 | Bucket owned có lifecycle hoặc lý do giữ; bucket out-of-scope có handoff | Apply lifecycle bừa, đụng tfstate/audit sai |
| Telemetry | Retention hữu hạn, auditability còn, ingestion/cardinality có hướng kiểm soát | Tắt log/trace làm mù điều tra |
| SLO | Dashboard/kubectl/events sau action ổn | Cleanup làm tụt SLO hoặc mất observability |

## 10. Mẫu kết luận cho PR/Jira/mentor

```text
Mandate 18 tập trung hidden cost ngoài EC2 node compute.

Before evidence cho thấy:
- EBS available: <n> volume, <x> GiB
- EIP unattached: <n>
- Snapshot/AMI self-owned candidate: <n>
- LB/TG orphan candidate: <n>
- NAT/VPC endpoint: <summary>
- S3 lifecycle: <summary>
- CloudWatch/telemetry: <summary>

Action đã làm:
- <cleanup/optimization/decision>

Usage giảm:
- <x> GiB-month EBS
- <x> endpoint-hour/NAT-hour/data GB nếu có
- <x> log retention/stored bytes/ingestion nếu có

Guardrail:
- không tắt audit log cần cho Mandate 11/12
- không đụng tfstate current object
- không đụng resource chưa rõ owner
- SLO và observability sau action vẫn ổn
```

## 11. Câu trả lời oral ngắn

Nếu bị hỏi "Mandate 18 khác gì Mandate 13?":

> Mandate 13 cắt chi phí node compute bằng Spot/Karpenter/Graviton. Mandate 18 cắt phần hidden cost ngoài compute như EBS mồ côi, NAT/VPC endpoint, S3 lifecycle và telemetry. Khi làm 18 em loại EC2 Compute ra khỏi scope để không đếm trùng với 13.

Nếu bị hỏi "Tại sao không tắt audit log để giảm CloudWatch?":

> Vì yêu cầu vẫn phải giữ khả năng vận hành và điều tra. Audit log đang phục vụ Mandate 11/12 và incident investigation. Nếu cost nằm ở ingestion thì hạ retention không tiết kiệm nhiều; còn tắt audit log thì rẻ hơn nhưng làm mù hệ thống, nên không đạt tinh thần mandate.

Nếu bị hỏi "Evidence done là gì?":

> Done không phải chỉ là nói rẻ hơn. Done là có before/after inventory, có usage giảm hoặc decision giữ lại có lý do, có owner/approval, và chứng minh SLO/observability vẫn ổn sau khi cleanup.
