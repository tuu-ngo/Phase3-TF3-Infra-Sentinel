# Runbook — bảo trì node stateful (postgres/valkey) có kiểm soát

Bổ sung cho [runbook demo Mandate #3](mandate-03-drain-node-demo.md) — phần đó chỉ drain node **app**.
Đây là câu trả lời trung thực cho câu hỏi: *"vậy khi cần bảo trì chính node database thì sao?"*

## Sự thật cần nói thẳng

postgres + valkey là **single-replica + RWO PVC** trên **1 node stateful duy nhất** (`stateful_1a`,
`min=max=desired=1`, AZ `ap-southeast-1a`). Khi node đó cần bảo trì/thay:
- **Không thể zero-downtime** như tầng app. Sẽ có **cửa sổ downtime ~30-60s/datastore** (detach + reattach
  PVC + khởi động lại + warm-up). Đây là bản chất single-replica RWO, không phải thiếu sót cấu hình.
- Zero-downtime thật cho tầng data **cần replication** (RDS Multi-AZ / ElastiCache / operator kiểu
  CloudNativePG) — nằm ngoài ngân sách + thời hạn hiện tại. Đã ghi là roadmap trong [ADR 0002](../adr/0002-managed-services-evaluation.md)
  + [ADR 0007](../adr/0007-mandate-03-maintenance-no-downtime-cdo02.md).

Vì vậy chiến lược bảo trì tầng data = **downtime ngắn có kiểm soát trong cửa sổ off-peak**, giảm thiểu
bằng client retry, KHÔNG giả vờ zero-downtime.

## Giảm thiểu tác động khách (đã có sẵn)
- **Client retry/pool**: product-catalog dùng connection pool (tự reconnect); checkout publish Kafka
  `WaitForAll` + retry. Request trúng cửa sổ failover được thử lại thay vì lỗi ngay — một phần khách
  không nhận ra.
- **postgres:17.6 shutdown sạch**: SIGTERM → fast shutdown (checkpoint) trong grace 30s → không phải
  crash-recovery lúc khởi động lại → rút ngắn downtime.

## Quy trình A — chỉ restart/patch datastore, GIỮ node (downtime ngắn nhất ~10-30s)

Dùng khi chỉ cần restart postgres/valkey (vá config, đổi image) mà node vẫn tốt:
```sh
# off-peak. Xoa pod -> Deployment tao lai NGAY tren cung node, PVC reattach nhanh.
kubectl -n techx-tf3 delete pod -l opentelemetry.io/name=postgresql
kubectl -n techx-tf3 rollout status deploy/postgresql --timeout=120s
# lam tuong tu cho valkey-cart neu can
```

## Quy trình B — THAY node stateful (downtime ~30-60s/datastore)

Dùng khi phải thay chính node (nâng cấp AMI, đổi instance type, node lỗi phần cứng). PVC khoá AZ `1a`
nên node thay **bắt buộc cùng AZ 1a**.

1. **Tạo node stateful thứ 2 tạm thời** (managed node group đang `max_size=1`):
   ```sh
   # Terraform: tam thoi cho phep 2 node stateful
   cd infra/live/production
   terraform apply -var="stateful_node_max_size=2" -var="stateful_node_desired_size=2"  # neu da tham so hoa
   # HOAC bump truc tiep qua AWS console/CLI managed node group scaling config (nho revert sau)
   ```
   Chờ node 2 (AZ 1a) `Ready`:
   ```sh
   kubectl get nodes -l techx.io/workload=stateful -L topology.kubernetes.io/zone
   ```

2. **Cordon node cũ**, di dời từng datastore (làm lần lượt, không đồng thời):
   ```sh
   OLD=<node-stateful-cu>
   kubectl cordon "$OLD"
   # postgres truoc
   kubectl -n techx-tf3 delete pod -l opentelemetry.io/name=postgresql   # reschedule sang node stateful moi
   kubectl -n techx-tf3 rollout status deploy/postgresql --timeout=180s
   # xac nhan phuc vu lai truoc khi lam valkey
   kubectl -n techx-tf3 delete pod -l opentelemetry.io/name=valkey-cart
   kubectl -n techx-tf3 rollout status deploy/valkey-cart --timeout=180s
   ```

3. **Drain + gỡ node cũ**, thu node group về 1:
   ```sh
   kubectl drain "$OLD" --ignore-daemonsets --delete-emptydir-data --timeout=180s
   terraform apply   # tra stateful_node_max/desired ve 1 -> ASG terminate node cu
   ```

## Đo downtime thật (làm trong dry-run / demo, off-peak)

Trong lúc chạy Quy trình A hoặc B, đo cửa sổ mất kết nối từ client:
```sh
# vong lap do browse (phu thuoc postgres) + cart (phu thuoc valkey)
while true; do
  ts=$(date +%s.%N)
  code=$(curl -s -o /dev/null -m 3 -w "%{http_code}" https://d2tn71186d7ilz.cloudfront.net/api/products)
  echo "$ts $code"
  sleep 0.2
done | tee /tmp/failover-probe.log
```
Ghi số downtime thật (số giây có mã != 200) vào ADR 0007 làm bằng chứng — **báo cáo con số thật, không
làm tròn xuống**.

## Nghiệm thu
- postgres + valkey `Running` trên node stateful mới; PVC `Bound` lại đúng volume cũ (không mất data).
- Downtime đo được nằm trong ước tính (~30-60s/datastore) và xảy ra trong cửa sổ off-peak đã hẹn.
- Đối với mentor: trình bày trung thực — tầng app zero-downtime (đã chứng minh), tầng data downtime ngắn
  có kiểm soát + đường HA thật (RDS/ElastiCache) là quyết định ngân sách, không phải bỏ sót.
