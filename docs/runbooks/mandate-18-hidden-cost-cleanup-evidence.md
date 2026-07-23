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

## 2. Điều kiện tiên quyết

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

## 3. Deliverable phải nộp

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

## 4. Read-only inventory before action

### 4.1. EBS volumes

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

### 4.2. Verify EBS candidate không còn PV/PVC live

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

### 4.3. EIP unattached

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

### 4.4. Snapshot và AMI self-owned

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

### 4.5. Load balancer và target group orphan

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

### 4.6. NAT gateway và VPC endpoints

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

### 4.7. S3 lifecycle và owner matrix

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

### 4.8. CloudWatch logs và telemetry

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

### 4.9. Top non-compute cost drivers

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

## 5. Action gate trước khi cleanup hoặc optimize

Trước khi chạy bất kỳ lệnh thay đổi nào, phải có:

- owner tài nguyên;
- ticket hoặc PR/comment approve;
- before evidence đã chụp;
- rollback hoặc lý do không cần rollback;
- cửa sổ theo dõi SLO nếu có khả năng ảnh hưởng runtime.

Các lệnh dưới đây là ví dụ để owner chạy sau approval, không chạy trong bước inventory.

### 5.1. Delete EBS orphan sau approval

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

### 5.2. Release EIP unattached sau approval

```powershell
# Chỉ chạy nếu EIP không có AssociationId và owner xác nhận cleanup.
$AllocationId = "<allocation-id>"

aws ec2 release-address `
  --profile $env:AWS_PROFILE `
  --region $env:AWS_REGION `
  --allocation-id $AllocationId
```

### 5.3. Lifecycle S3 sau approval

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

## 6. SLO và vận hành sau cleanup

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

## 7. Checklist evidence done

Mandate 18 có thể coi là có evidence tốt khi có đủ:

- [ ] before inventory EBS/EIP/snapshot/AMI/LB/TG;
- [ ] before inventory NAT/VPC endpoint;
- [ ] before inventory S3 lifecycle và owner matrix;
- [ ] before inventory CloudWatch/telemetry retention;
- [ ] top non-compute cost-driver được chỉ ra;
- [ ] ít nhất một cleanup/optimization thật hoặc decision record giữ lại có lý do;
- [ ] after inventory chứng minh resource/usage đã giảm;
- [ ] SLO/observability sau action vẫn ổn;
- [ ] phần compute node cost được loại khỏi scope để không đếm trùng Mandate 13;
- [ ] residual risk và owner handoff được ghi rõ.

## 8. Mẫu kết luận cho PR/Jira/mentor

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

## 9. Câu trả lời oral ngắn

Nếu bị hỏi "Mandate 18 khác gì Mandate 13?":

> Mandate 13 cắt chi phí node compute bằng Spot/Karpenter/Graviton. Mandate 18 cắt phần hidden cost ngoài compute như EBS mồ côi, NAT/VPC endpoint, S3 lifecycle và telemetry. Khi làm 18 em loại EC2 Compute ra khỏi scope để không đếm trùng với 13.

Nếu bị hỏi "Tại sao không tắt audit log để giảm CloudWatch?":

> Vì yêu cầu vẫn phải giữ khả năng vận hành và điều tra. Audit log đang phục vụ Mandate 11/12 và incident investigation. Nếu cost nằm ở ingestion thì hạ retention không tiết kiệm nhiều; còn tắt audit log thì rẻ hơn nhưng làm mù hệ thống, nên không đạt tinh thần mandate.

Nếu bị hỏi "Evidence done là gì?":

> Done không phải chỉ là nói rẻ hơn. Done là có before/after inventory, có usage giảm hoặc decision giữ lại có lý do, có owner/approval, và chứng minh SLO/observability vẫn ổn sau khi cleanup.
