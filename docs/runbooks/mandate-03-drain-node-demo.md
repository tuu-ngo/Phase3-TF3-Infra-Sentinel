# Runbook — Mandate #3: demo drain node không downtime + monitor SLO

Dùng để **tự thực hiện trước mặt mentor**: drain 1 node app-tier giữa giờ, cho thấy luồng browse →
cart → checkout giữ SLO. Cơ sở kỹ thuật: [ADR 0007](../adr/0007-mandate-03-maintenance-no-downtime-cdo02.md).

**Nguyên tắc:** drain **node APP tier**, KHÔNG drain node stateful (`stateful_1a` chứa postgres+valkey —
single-replica, sẽ blip; residual risk đã ghi trong ADR 0007). Chọn node có nhiều pod revenue nhất để
demo có ý nghĩa.

## 0. Chuẩn bị truy cập

```sh
# Tunnel EKS API (SSM) — hoặc dùng Cloudflare access nếu đã cấu hình kubectl
aws ssm start-session --target <bastion_instance_id> \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters host="<cluster_endpoint>",portNumber="443",localPortNumber="8443" \
  --region ap-southeast-1
# terminal khác:
aws eks update-kubeconfig --name techx-corp-tf3 --region ap-southeast-1
kubectl config set-cluster arn:aws:eks:ap-southeast-1:197826770971:cluster/techx-corp-tf3 \
  --server=https://localhost:8443 --insecure-skip-tls-verify=true
```

Grafana SLO dashboard (mở sẵn trên màn hình cho mentor xem suốt demo):
**https://grafana.arthur-ngo.org** → dashboard **SLO**.

## 1. Pre-flight — xác nhận đã drain-safe TRƯỚC khi bắt đầu

```sh
# a) Mỗi service revenue có 2 replica ở 2 node/AZ khác nhau (nhờ topologySpread)
kubectl -n techx-tf3 get pods -o wide \
  -l 'opentelemetry.io/name in (frontend,frontend-proxy,product-catalog,cart,checkout,payment,currency,shipping,quote,product-reviews)' \
  --sort-by=.spec.nodeName

# b) PDB đều ALLOWED DISRUPTIONS >= 1
kubectl -n techx-tf3 get pdb

# c) chọn node app-tier để drain (KHÔNG phải node có nhãn techx.io/workload=stateful)
kubectl get nodes -L techx.io/workload,topology.kubernetes.io/zone
```

**Điều kiện đi tiếp:** mỗi service revenue có replica nằm trên ≥2 node khác nhau; node định drain KHÔNG
có nhãn `techx.io/workload=stateful`; PDB không có cái nào `ALLOWED DISRUPTIONS = 0`.

## 2. Baseline SLO (chụp trước khi drain)

Trên Grafana SLO dashboard, ghi nhận mức hiện tại: checkout success-rate, browse/cart success-rate,
storefront p95. Đây là mốc so sánh. (Nếu có load-generator chạy nền ở mức nhẹ để có traffic thật trong
lúc demo thì SLO có ý nghĩa hơn — bật ~20-50 user, không cần 200.)

## 3. Drain node (thao tác chính, trước mặt mentor)

```sh
NODE=<node-app-tier-đã-chọn-ở-1c>

# cordon: không cho pod mới xuống node này
kubectl cordon "$NODE"

# drain: đuổi pod đi (tôn trọng PDB + graceful preStop). Bỏ qua DaemonSet + emptyDir.
kubectl drain "$NODE" \
  --ignore-daemonsets \
  --delete-emptydir-data \
  --grace-period=30 \
  --timeout=180s
```

Trong lúc drain, **theo dõi liên tục**:
```sh
# pod revenue được reschedule sang node khác, luôn còn bản Ready phục vụ
watch -n2 "kubectl -n techx-tf3 get pods -o wide \
  -l 'opentelemetry.io/name in (frontend,cart,checkout,product-catalog)' --sort-by=.spec.nodeName"
```
+ mắt nhìn Grafana SLO dashboard — đường success-rate KHÔNG được rớt dưới ngưỡng, p95 không vọt >1s.

**Vì sao không rớt:** topologySpread đảm bảo replica còn lại ở node khác vẫn phục vụ; PDB chặn đuổi quá
số cho phép; `preStop sleep 5s` cho pod đang tắt xử lý nốt request dở; readinessProbe đảm bảo pod mới
chỉ nhận traffic khi đã sẵn sàng.

## 4. Nghiệm thu

```sh
# tất cả pod revenue Running trở lại (trên các node còn lại), 0 pod Pending kẹt
kubectl -n techx-tf3 get pods -o wide | grep -Ev "Running|Completed" || echo "OK: khong con pod loi"
```
Trên Grafana: xác nhận trong toàn bộ cửa sổ drain, checkout ≥99% / browse-cart ≥99.5% / p95 <1s. Mentor
thấy SLO không rớt + cách team monitor → **confirm OK là đạt**.

## 5. Khôi phục (sau demo)

```sh
kubectl uncordon "$NODE"     # cho phép schedule lại lên node này
```
Node quay lại pool. Nếu là managed node group và muốn "thay node" thật (mô phỏng thay phần cứng), có thể
terminate instance để ASG tạo node mới — pod đã ở node khác nên không ảnh hưởng. Không bắt buộc cho demo.

## Lưu ý an toàn
- KHÔNG drain node `stateful_1a` trong demo (postgres+valkey single-replica → blip, ngoài phạm vi chứng
  minh app-tier). Nếu mentor yêu cầu thử node stateful: nói rõ đây là residual risk đã ghi (ADR 0007),
  đường HA thật là RDS/ElastiCache — không giả vờ zero-downtime cho single-replica datastore.
- KHÔNG đụng flagd, không đổi cấu hình ops-exposure trong lúc demo.
