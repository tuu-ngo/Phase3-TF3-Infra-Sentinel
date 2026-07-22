# Runbook: T10 — SA Migration (22 ServiceAccount riêng)

> **Mục tiêu:** Migrate từng service một sang SA riêng, theo dõi sau mỗi bước.
> **Thời gian ước tính:** 2-3h (bao gồm verify từng wave)
> **Rủi ro:** Thấp nếu theo đúng thứ tự. Rollback < 2 phút mỗi service.

---

## Lệnh deploy chuẩn (dùng cho mọi wave)

```bash
helm upgrade techx-corp \
  "phase3 - information/techx-corp-chart" \
  --set default.image.repository=197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp \
  -f "phase3 - information/deploy/values-flagd-sync.yaml" \
  -f "phase3 - information/deploy/values-prod.yaml" \
  -f "phase3 - information/deploy/values-serviceaccounts.yaml" \
  -n techx-tf3 \
  --wait --timeout 180s
```

> ⚠️ Thứ tự `-f` quan trọng: `values-prod.yaml` trước, `values-serviceaccounts.yaml` sau.
> Helm deep-merge: key trùng → file sau thắng; key không trùng → giữ nguyên.

---

## Lệnh rollback (nếu có lỗi bất kỳ wave nào)

```bash
# Option A: Rollback toàn bộ release về revision trước
helm rollback techx-corp -n techx-tf3
helm rollback techx-corp <REVISION_CỤ_THỂ> -n techx-tf3

# Xem lịch sử revision
helm history techx-corp -n techx-tf3
```

---

## Trước khi bắt đầu

```bash
# 1. Ghi lại revision hiện tại làm checkpoint rollback
helm history techx-corp -n techx-tf3 | tail -3

# 2. Xác nhận tất cả pod đang Running
kubectl get pods -n techx-tf3 --no-headers | grep -v Running

# 3. Xác nhận SA hiện tại
kubectl get sa -n techx-tf3

# 4. Xác nhận SLO checkout đang ổn (kiểm tra Grafana trước khi bắt đầu)
kubectl -n techx-tf3 port-forward svc/grafana 3000:80 &
# Mở http://localhost:3000 → kiểm tra checkout success rate
```

---

## WAVE 1 — Stateless, không trên critical path (thấp nhất)

**Services:** `image-provider`, `ad`, `recommendation`, `quote`, `currency`, `email`, `shipping`, `load-generator`

Tất cả 8 service này đã được uncomment trong `values-serviceaccounts.yaml` — deploy 1 lần.

```bash
# Deploy
helm upgrade techx-corp "phase3 - information/techx-corp-chart" \
  --set default.image.repository=197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp \
  -f "phase3 - information/deploy/values-flagd-sync.yaml" \
  -f "phase3 - information/deploy/values-prod.yaml" \
  -f "phase3 - information/deploy/values-serviceaccounts.yaml" \
  -n techx-tf3 --wait --timeout 180s

# Verify từng service
for svc in image-provider ad recommendation quote currency email shipping load-generator; do
  echo "=== Verifying: $svc ==="
  ./scripts/verify-sa-migration.sh "$svc" || { echo "STOP: $svc failed"; break; }
  sleep 5
done
```

---

## WAVE 2 — AI/ML service

**Service:** `llm`

```bash
# llm đã có trong values-serviceaccounts.yaml, được deploy cùng Wave 1
./scripts/verify-sa-migration.sh llm
```

---

## WAVE 3 — Data read path (DB readers)

**Services:** `product-catalog`, `product-reviews`

```bash
# Đã có trong values-serviceaccounts.yaml
./scripts/verify-sa-migration.sh product-catalog
./scripts/verify-sa-migration.sh product-reviews
```

---

## WAVE 4 — Frontend layer

**Services:** `frontend`, `frontend-proxy`

> ⚠️ `frontend` có `replicas: 2` và topology spread. Rollout sẽ rotate 2 pod.
> Với `maxUnavailable: 0, maxSurge: 1`, tổng pods tạm thời lên 3 trong lúc rollout.

```bash
./scripts/verify-sa-migration.sh frontend
./scripts/verify-sa-migration.sh frontend-proxy
```

---

## WAVE 5 — Async Kafka consumers

**Services:** `fraud-detection`, `accounting`

```bash
./scripts/verify-sa-migration.sh fraud-detection
./scripts/verify-sa-migration.sh accounting

# Sau khi accounting migrate, kiểm tra Kafka consumer lag không tăng
kubectl exec -n techx-tf3 deploy/kafka -- \
  sh -c "KAFKA_OPTS='' /opt/kafka/bin/kafka-consumer-groups.sh \
    --bootstrap-server localhost:9092 \
    --describe --group accounting 2>/dev/null"
# Mong đợi: LAG = 0
```

---

## WAVE 6 — Revenue-critical path

> ⚠️ Thực hiện từng service, **không deploy cùng nhau**.
> Kiểm tra Grafana checkout SLO sau mỗi service.

### payment

```bash
./scripts/verify-sa-migration.sh payment

# Smoke test checkout vẫn hoạt động
curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/api/products
# Mong đợi: 200
```

### checkout (SPECIAL — Argo Rollouts)

> ⚠️ `checkout` dùng Argo Rollouts. Helm upgrade chỉ update Deployment spec,
> nhưng Rollout object phải được patch riêng.

```bash
# Bước 1: Helm upgrade tạo SA techx-checkout và update Deployment spec
helm upgrade techx-corp "phase3 - information/techx-corp-chart" \
  --set default.image.repository=197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp \
  -f "phase3 - information/deploy/values-flagd-sync.yaml" \
  -f "phase3 - information/deploy/values-prod.yaml" \
  -f "phase3 - information/deploy/values-serviceaccounts.yaml" \
  -n techx-tf3 --wait --timeout 180s

# Bước 2: Patch Rollout để dùng SA mới
kubectl -n techx-tf3 patch rollout checkout \
  --type=merge \
  -p '{"spec":{"template":{"spec":{"serviceAccountName":"techx-checkout"}}}}'

# Bước 3: Theo dõi Rollout promote
kubectl -n techx-tf3 get rollout checkout -w

# Bước 4: Verify
./scripts/verify-sa-migration.sh checkout
```

### cart

> ⚠️ `cart` có `replicas: 2`, người dùng đang dùng session có thể bị reset nếu
> cả 2 pod rotate cùng lúc. Với `maxUnavailable: 0` điều này không xảy ra.

```bash
./scripts/verify-sa-migration.sh cart

# Kiểm tra cart vẫn hoạt động
curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/cart
# Mong đợi: 200
```

---

## WAVE 7 — Stateful infrastructure

> ⚠️ Đây là các pod stateful. SA thay đổi không ảnh hưởng data,
> nhưng pod restart cần được quản lý cẩn thận.

### kafka (SPECIAL — Recreate strategy)

> ⚠️ Kafka dùng `strategy: Recreate`. Pod cũ bị terminate TRƯỚC khi pod mới tạo.
> Trong khoảng 30-60s Kafka không available → checkout sẽ buffer orders.
> **Thực hiện ngoài giờ cao điểm.**

```bash
# Kiểm tra không có lag trước khi bắt đầu
kubectl exec -n techx-tf3 deploy/kafka -- \
  sh -c "KAFKA_OPTS='' /opt/kafka/bin/kafka-consumer-groups.sh \
    --bootstrap-server localhost:9092 \
    --describe --all-groups 2>/dev/null"

# Deploy
helm upgrade ... (lệnh chuẩn)

# Theo dõi pod terminate và tạo lại
kubectl get pods -n techx-tf3 -l opentelemetry.io/name=kafka -w

# Verify
./scripts/verify-sa-migration.sh kafka

# Kiểm tra lag sau restart (consumer cần reconnect)
sleep 30
kubectl exec -n techx-tf3 deploy/kafka -- \
  sh -c "KAFKA_OPTS='' /opt/kafka/bin/kafka-consumer-groups.sh \
    --bootstrap-server localhost:9092 \
    --describe --all-groups 2>/dev/null"
# Mong đợi: LAG = 0 sau ~30s consumers reconnect
```

### valkey-cart

```bash
./scripts/verify-sa-migration.sh valkey-cart

# Kiểm tra cart vẫn đọc được session
curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/cart
```

### postgresql

> ⚠️ PostgreSQL restart sẽ làm product-catalog, product-reviews, accounting
> mất DB connection tạm thời (~10-30s). Chúng sẽ tự reconnect.

```bash
# Theo dõi pod postgresql trong lúc rollout
kubectl get pods -n techx-tf3 -l opentelemetry.io/name=postgresql -w &

./scripts/verify-sa-migration.sh postgresql

# Kiểm tra product-catalog vẫn trả data
curl -s http://localhost:8080/api/products | python -c "import json,sys; d=json.load(sys.stdin); print(f'Products: {len(d)}')"
# Mong đợi: Products: <số > 0>
```

---

## WAVE 8 — flagd (CUỐI CÙNG)

> ⚠️ flagd giữ BTC sync token. Migrate cuối cùng để tránh rủi ro.
> Token sync là Bearer token trong pod args — KHÔNG phải K8s SA token.
> automountServiceAccountToken: false an toàn, không ảnh hưởng BTC sync.

```bash
./scripts/verify-sa-migration.sh flagd

# Kiểm tra flagd log đặc biệt
kubectl logs -n techx-tf3 deploy/flagd --tail=30
# Mong đợi: sync activity, không có "Forbidden" hay "auth error"
```

---

## Sau khi hoàn thành tất cả waves

```bash
# 1. Xác nhận tất cả 22 SA đã tồn tại
kubectl get sa -n techx-tf3 | grep techx-
# Mong đợi: 22 SA techx-* + các SA của dependency chart

# 2. Xác nhận SA cũ techx-corp vẫn tồn tại (chưa xóa)
kubectl get sa techx-corp -n techx-tf3

# 3. Xác nhận không pod nào còn dùng SA cũ
kubectl get pods -n techx-tf3 \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.serviceAccountName}{"\n"}{end}' \
  | grep "techx-corp$"
# Mong đợi: KHÔNG có output (không pod nào còn dùng techx-corp cũ)

# 4. Xác nhận không pod nào còn mount token
for pod in $(kubectl get pods -n techx-tf3 -o name | grep -v "otel-collector\|prometheus\|grafana\|jaeger\|opensearch"); do
  result=$(kubectl exec -n techx-tf3 "$pod" -- \
    ls /var/run/secrets/kubernetes.io/serviceaccount/ 2>&1 || true)
  if ! echo "$result" | grep -qiE "No such file|cannot access|not found"; then
    echo "WARNING: $pod vẫn mount token: $result"
  fi
done

# 5. Chạy smoke test cuối
curl -s -o /dev/null -w "%{http_code}" http://localhost:8080 && echo " /"
curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/api/products && echo " /api/products"
curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/cart && echo " /cart"
```

---

## Cleanup SA cũ (làm sau khi stable 24h)

```bash
# Chỉ chạy sau khi đã xác nhận KHÔNG pod nào dùng SA cũ (bước 3 ở trên)
kubectl delete sa techx-corp -n techx-tf3

# Xác nhận xóa xong
kubectl get sa -n techx-tf3 | grep -v techx-
```

---

## Troubleshooting

### Pod không start sau khi đổi SA

```bash
kubectl describe pod -n techx-tf3 -l opentelemetry.io/name=<service>
# Nhìn vào Events: có "serviceaccount not found" không?
```

Nguyên nhân: SA mới chưa được tạo trước khi pod schedule. Thường do helm upgrade bị lỗi giữa chừng.

Fix:
```bash
# Kiểm tra SA tồn tại
kubectl get sa techx-<service> -n techx-tf3

# Nếu không có: tạo thủ công để pod schedule được
kubectl create sa techx-<service> -n techx-tf3
# Sau đó helm upgrade lại bình thường
```

### checkout Rollout không update SA

```bash
# Kiểm tra SA hiện tại của Rollout
kubectl get rollout checkout -n techx-tf3 \
  -o jsonpath='{.spec.template.spec.serviceAccountName}'

# Patch thủ công nếu cần
kubectl -n techx-tf3 patch rollout checkout \
  --type=merge \
  -p '{"spec":{"template":{"spec":{"serviceAccountName":"techx-checkout"}}}}'
```

### Token vẫn mount dù SA có automount: false

Nguyên nhân: pod spec có `automountServiceAccountToken: true` tường minh, override SA setting.

```bash
# Kiểm tra pod spec
kubectl get pod -n techx-tf3 <pod-name> \
  -o jsonpath='{.spec.automountServiceAccountToken}'

# Nếu = true: cần thêm vào values-serviceaccounts.yaml cho component đó
# components:
#   <service>:
#     serviceAccount:
#       automountServiceAccountToken: false
#     podSpec:          ← level pod spec
#       automountServiceAccountToken: false
```
