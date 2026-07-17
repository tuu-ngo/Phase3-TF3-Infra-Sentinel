# T10 — Kế hoạch migration: 22 ServiceAccount riêng, rolling từng service

> **Chiến lược:** Tạo 22 SA riêng → chuyển từng service một → theo dõi log → giữ hoặc rollback.
> Không đổi tất cả cùng lúc để giảm blast radius nếu có lỗi.
>
> **Điều kiện tiên quyết:**
> - Chart đã hỗ trợ sẵn per-component `serviceAccount` override (xác nhận qua `component.yaml`).
> - Khi component có key `serviceAccount:`, chart tự tạo SA riêng với tên = SA name, không dùng SA chung.
> - Không có service nào gọi K8s API → `automountServiceAccountToken: false` cho tất cả.

---

## Cơ chế hoạt động trong chart

```yaml
# component.yaml logic (đã có sẵn):
{{- if hasKey $config "serviceAccount" }}
    {{- $serviceAccount = mergeOverwrite (deepCopy $.Values.serviceAccount) $config.serviceAccount }}
    {{- $componentScopedServiceAccount = true }}
{{- end }}
# → Khi true: chart gọi techx-corp.componentServiceAccount → tạo SA riêng
# → _objects.tpl dùng SA riêng đó cho Deployment
```

Chỉ cần thêm block `serviceAccount:` vào từng component trong `values.yaml` là đủ.
Không cần sửa template file nào.

---

## Thứ tự migration theo rủi ro (thấp → cao)

| Thứ tự | Service | Lý do ưu tiên |
|---|---|---|
| 1 | `image-provider` | Stateless, serve ảnh tĩnh — rủi ro thấp nhất |
| 2 | `ad` | Stateless, không trên checkout path |
| 3 | `recommendation` | Stateless, chỉ đọc catalog |
| 4 | `quote` | Stateless, tính giá ship đơn giản |
| 5 | `currency` | Stateless, convert tiền |
| 6 | `email` | Gửi email, không có state |
| 7 | `shipping` | Tính ship, không có state |
| 8 | `load-generator` | Tool test, không phải production |
| 9 | `llm` | AI service, isolated |
| 10 | `product-catalog` | Đọc DB, medium risk |
| 11 | `product-reviews` | Đọc DB, medium risk |
| 12 | `frontend` | Web frontend, medium risk |
| 13 | `frontend-proxy` | Envoy gateway — quan trọng hơn nhưng không có state |
| 14 | `fraud-detection` | Kafka consumer |
| 15 | `accounting` | Kafka consumer + DB write |
| 16 | `payment` | Revenue critical |
| 17 | `checkout` | Revenue critical, orchestrator |
| 18 | `cart` | Session state |
| 19 | `kafka` | Message broker |
| 20 | `valkey-cart` | Cache stateful |
| 21 | `postgresql` | Database stateful |
| 22 | `flagd` | BTC sync — migrate cuối cùng, thận trọng nhất |

---

## Cách áp từng service

### Pattern chung — thêm vào values.yaml

```yaml
components:
  <service-name>:
    # ... các config hiện có giữ nguyên ...
    serviceAccount:
      create: true
      name: "techx-<service-name>"
      annotations: {}
      automountServiceAccountToken: false
```

### Lệnh deploy từng service (ví dụ image-provider)

```bash
helm upgrade techx-corp ./techx-corp-chart \
  --set default.image.repository=<ECR> \
  -f deploy/values-flagd-sync.yaml \
  -n techx-tf3 \
  --wait --timeout 120s
```

### Lệnh kiểm tra ngay sau rollout

```bash
# 1. SA mới đã tồn tại chưa?
kubectl get sa -n techx-tf3 | grep techx-

# 2. Pod đang dùng SA nào?
kubectl get pod -n techx-tf3 -l opentelemetry.io/name=<service> \
  -o jsonpath='{.items[0].spec.serviceAccountName}'

# 3. Token không còn mount không?
kubectl exec -n techx-tf3 deploy/<service> -- \
  ls /var/run/secrets/kubernetes.io/serviceaccount/ 2>&1

# 4. Log có lỗi 403/401 không?
kubectl logs -n techx-tf3 deploy/<service> --tail=50 | \
  grep -E "403|401|Forbidden|Unauthorized"

# 5. Pod stable không?
kubectl rollout status deploy/<service> -n techx-tf3
```

### Tiêu chí pass/fail

| Kiểm tra | Pass | Fail → hành động |
|---|---|---|
| `rollout status` | `successfully rolled out` | `helm rollback` ngay |
| SA token mount | `No such file or directory` | OK — đúng hành vi mong muốn |
| Log 403/Forbidden | Không xuất hiện | Rollback + điều tra |
| Log 401/Unauthorized | Không xuất hiện | Rollback + điều tra |
| Pod ready | `1/1 Running`, restart=0 | Nếu restart > 0: xem log trước khi quyết định |
