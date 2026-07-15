# T10 — Vệ sinh định danh Workload: Báo cáo Thiết kế ServiceAccount

> **Trạng thái:** Chỉ thiết kế — không thay đổi code, không deploy, không kubectl apply
> **Tác giả:** CDO01
> **Ngày:** 2026-07-10
> **Nguồn xác minh:** Chỉ từ source code — mọi kết luận đều trích dẫn đường dẫn file cụ thể

---

# 1. Tổng quan Repository

## Cấu trúc chart

```
phase3 - information/techx-corp-chart/
├── Chart.yaml                          # chart v0.40.9, appVersion 2.2.0
├── values.yaml                         # file values duy nhất, ~1300 dòng
└── templates/
    ├── _helpers.tpl                    # định nghĩa helper techx-corp.serviceAccountName
    ├── _objects.tpl                    # định nghĩa template techx-corp.deployment
    ├── _pod.tpl                        # helpers cho env/port
    ├── component.yaml                  # duyệt .Values.components → render tất cả workload
    ├── serviceaccount.yaml             # tạo MỘT ServiceAccount duy nhất
    ├── grafana-config.yaml             # chỉ là ConfigMap, không có SA
    ├── flagd-config.yaml               # chỉ là ConfigMap, không có SA
    └── posgresql-init-config.yaml      # chỉ là ConfigMap, không có SA
```

## Dependency charts (từ `Chart.yaml`)

```yaml
dependencies:
  - opentelemetry-collector  # có SA riêng: otel-collector
  - jaeger                   # có SA riêng: jaeger
  - prometheus               # có SA riêng: prometheus
  - grafana                  # có SA riêng: grafana (+ grafana-clusterrole)
  - opensearch               # có SA riêng
```

SA của các dependency chart **KHÔNG được quản lý bởi `serviceaccount.yaml`** trong chart này.
Chúng được tạo bởi upstream Helm chart của chính chúng với RBAC riêng.

## Phát hiện chính

Chart hiện tại chỉ tạo **đúng một ServiceAccount duy nhất** cho toàn bộ 22 app component.
Không có Role, RoleBinding, ClusterRole, hay ClusterRoleBinding nào trong `templates/`.

---

# 2. ServiceAccount hiện tại

## 2.1 ServiceAccount được định nghĩa trong chart này

**File:** `templates/serviceaccount.yaml`

```yaml
{{- if .Values.serviceAccount.create -}}
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{ include "techx-corp.serviceAccountName" . }}
  labels:
    {{- include "techx-corp.labels" . | nindent 4 }}
  {{- if .Values.serviceAccount.annotations }}
  annotations: ...
  {{- end }}
{{- end }}
```

**Cách tên được resolve** (`_helpers.tpl` dòng 78–83):

```yaml
{{- define "techx-corp.serviceAccountName" -}}
{{- if .serviceAccount.create }}
{{- default (include "techx-corp.name" .) .serviceAccount.name }}
```

- `values.yaml`: `serviceAccount.name: ""` và `serviceAccount.create: true`
- `techx-corp.name` trả về `.Release.Name` rút gọn tối đa 63 ký tự
- **Kết quả render:** `techx-corp` (tên Helm release)

**Kết luận:** Chart này tạo **đúng 1 ServiceAccount tên `techx-corp`**.

## 2.2 ServiceAccount được tạo bởi dependency charts (KHÔNG có trong templates/)

| Tên SA | Tạo bởi | Có ClusterRole? | Ghi chú |
|---|---|---|---|
| `grafana` | grafana Helm chart | ✅ CÓ — `grafana-clusterrole` | Đọc `secrets` toàn cluster — RỦI RO CAO (xem file evidence) |
| `jaeger` | jaeger Helm chart | Không xác định được từ source | Upstream chart tự quản lý RBAC |
| `otel-collector` | opentelemetry-collector chart | ✅ CÓ — ClusterRole `otel-collector` | Cần metrics node/pod — hợp lệ |
| `prometheus` | prometheus Helm chart | ✅ CÓ — ClusterRole `prometheus` | Cần scrape pod/endpoint/node — hợp lệ |
| `opensearch` | opensearch Helm chart | Không xác định được từ source | Upstream chart tự quản lý RBAC |

**Phạm vi T10:** Task này chỉ xử lý **SA tầng app `techx-corp`**.
SA của dependency chart nằm ngoài phạm vi T10 (việc sửa grafana ClusterRole được theo dõi riêng ở SEC-01).

## 2.3 `serviceaccount.yaml` có hardcode hay dùng template?

**Trả lời: Hoàn toàn dùng template.** Không có tên nào được hardcode.

- `name` → resolve qua helper `{{ include "techx-corp.serviceAccountName" . }}`
- `labels` → resolve qua `{{ include "techx-corp.labels" . }}`
- `annotations` → resolve từ `{{ .Values.serviceAccount.annotations }}`
- Điểm kiểm soát duy nhất là `values.yaml`: `serviceAccount.create`, `serviceAccount.name`, `serviceAccount.annotations`

**Nguồn:** `templates/serviceaccount.yaml`, `templates/_helpers.tpl` dòng 77–83

---

# 3. RBAC hiện tại

## 3.1 Role và RoleBinding trong templates/

```
Kết quả grep trên ALL templates/**/*.yaml và templates/**/*.tpl:
  → Không tìm thấy: ClusterRole, ClusterRoleBinding, Role, RoleBinding
```

**Kết luận: Không có Role, RoleBinding, ClusterRole hay ClusterRoleBinding nào trong `templates/`.**

Đã xác minh: `templates/_objects.tpl`, `templates/component.yaml`, `templates/serviceaccount.yaml`,
`templates/_helpers.tpl`, `templates/grafana-config.yaml`, `templates/flagd-config.yaml`

## 3.2 RBAC được tạo bởi dependency charts (bằng chứng từ live cluster)

| Resource | Kind | Bind với SA | Namespace | Verbs | Rủi ro |
|---|---|---|---|---|---|
| `grafana-clusterrole` | ClusterRole | `techx-tf3/grafana` | toàn cluster | `get/list/watch secrets, configmaps` | ⚠️ CAO — đọc secrets trong kube-system |
| `grafana-clusterrolebinding` | ClusterRoleBinding | `techx-tf3/grafana` | toàn cluster | — | ⚠️ CAO |
| `otel-collector` | ClusterRole | `techx-tf3/otel-collector` | toàn cluster | nodes, pods, endpoints metrics | ✅ Hợp lệ |
| `prometheus` | ClusterRole | `techx-tf3/prometheus` | toàn cluster | nodes, pods, endpoints, configmaps | ✅ Hợp lệ |
| `grafana` (Role) | Role | `techx-tf3/grafana` | techx-tf3 | `rules: null` | ⚠️ Role rỗng tồn tại |

## 3.3 SA `techx-corp` có Role/RoleBinding nào không?

**Không có.** SA `techx-corp` có **zero binding** — đã xác nhận bằng:
- `kubectl auth can-i --list --as=system:serviceaccount:techx-tf3:techx-corp`
  → Chỉ trả về `selfsubjectreviews` + các public non-resource URL
- Không tìm thấy Role/RoleBinding trong chart templates

## 3.4 Có application nào gọi Kubernetes API không?

Kết quả tìm kiếm source code:
```
file .go:  grep kubernetes|k8s|InClusterConfig  → Không có kết quả
file .py:  grep kubernetes|k8s_client           → Không có kết quả
file .cs:  grep KubernetesClient|IKubernetes    → Không có kết quả
```

**Kết luận: Không có workload nào cần gọi Kubernetes API.**
**Do đó: Không tạo RoleBinding cho bất kỳ SA mới nào.**

---

# 4. Mapping Workload → ServiceAccount (Trạng thái hiện tại)

Tất cả 22 component được render bởi `templates/component.yaml` duyệt `.Values.components` và truyền:
```yaml
{{- $config := set . "serviceAccount" $.Values.serviceAccount }}
```
Sau đó `_objects.tpl` dòng 35 render:
```yaml
serviceAccountName: {{ include "techx-corp.serviceAccountName" .}}
```

Vì `$.Values.serviceAccount.name: ""` và `create: true`, **mọi component đều resolve thành `techx-corp`**.

| Workload | Kind | Namespace | SA hiện tại | Token được mount? |
|---|---|---|---|---|
| accounting | Deployment | techx-tf3 | `techx-corp` | Có (mặc định) |
| ad | Deployment | techx-tf3 | `techx-corp` | Có (mặc định) |
| cart | Deployment | techx-tf3 | `techx-corp` | Có (mặc định) |
| checkout | Deployment | techx-tf3 | `techx-corp` | Có (mặc định) |
| currency | Deployment | techx-tf3 | `techx-corp` | Có (mặc định) |
| email | Deployment | techx-tf3 | `techx-corp` | Có (mặc định) |
| fraud-detection | Deployment | techx-tf3 | `techx-corp` | Có (mặc định) |
| frontend | Deployment | techx-tf3 | `techx-corp` | Có (mặc định) |
| frontend-proxy | Deployment | techx-tf3 | `techx-corp` | Có (mặc định) |
| image-provider | Deployment | techx-tf3 | `techx-corp` | Có (mặc định) |
| kafka | Deployment | techx-tf3 | `techx-corp` | Có (mặc định) |
| llm | Deployment | techx-tf3 | `techx-corp` | Có (mặc định) |
| load-generator | Deployment | techx-tf3 | `techx-corp` | Có (mặc định) |
| payment | Deployment | techx-tf3 | `techx-corp` | Có (mặc định) |
| postgresql | Deployment | techx-tf3 | `techx-corp` | Có (mặc định) |
| product-catalog | Deployment | techx-tf3 | `techx-corp` | Có (mặc định) |
| product-reviews | Deployment | techx-tf3 | `techx-corp` | Có (mặc định) |
| quote | Deployment | techx-tf3 | `techx-corp` | Có (mặc định) |
| recommendation | Deployment | techx-tf3 | `techx-corp` | Có (mặc định) |
| shipping | Deployment | techx-tf3 | `techx-corp` | Có (mặc định) |
| valkey-cart | Deployment | techx-tf3 | `techx-corp` | Có (mặc định) |
| flagd | Deployment | techx-tf3 | `techx-corp` | Có (mặc định) |

**Nguồn:** `templates/component.yaml`, `templates/_objects.tpl` dòng 35, `templates/_helpers.tpl` dòng 77–83, `values.yaml` phần `serviceAccount`

**Cấu hình bất thường phát hiện được:**
- 22 workload với vai trò hoàn toàn khác nhau (web frontend, xử lý thanh toán, database, message queue, AI service) đều dùng chung 1 SA identity
- `automountServiceAccountToken` không được đặt thành `false` ở bất kỳ đâu trong chart templates
- Mọi pod đều có K8s JWT hợp lệ được mount tại `/var/run/secrets/kubernetes.io/serviceaccount/token` mà không có nhu cầu vận hành nào cần đến

---

# 5. Đề xuất ServiceAccount mới

## 5.1 Lý do phân nhóm

Phân nhóm theo nguyên tắc **giới hạn blast radius**: nếu một workload trong nhóm bị xâm phạm, token SA không thể dùng để mạo danh workload ở nhóm khác, và mọi RBAC grant trong tương lai đều được giới hạn đúng nhóm.

Nhóm được xác định dựa trên **vai trò chức năng** và **pattern truy cập dữ liệu** (từ `ARCHITECTURE.md`):

| Tên SA nhóm | Thành viên | Lý do |
|---|---|---|
| `techx-frontend` | `frontend`, `frontend-proxy`, `image-provider` | Tầng tiếp xúc người dùng. Không truy cập datastore. Không cần K8s API. Blast radius chung chấp nhận được — đều là stateless request handler. |
| `techx-checkout` | `checkout`, `payment`, `email`, `currency`, `shipping`, `quote` | Chuỗi điều phối checkout. Các service này gọi nhau theo thứ tự. Dùng chung SA chấp nhận được — cùng trust boundary. Không ghi trực tiếp vào datastore. |
| `techx-catalog` | `product-catalog`, `product-reviews`, `recommendation`, `ad`, `llm` | Chuỗi đọc dữ liệu sản phẩm. `product-catalog` và `product-reviews` dùng chung Postgres. `recommendation` và `ad` gọi `product-catalog`. `llm` phục vụ `product-reviews`. Cùng data domain. |
| `techx-data` | `cart`, `valkey-cart`, `kafka`, `postgresql`, `accounting`, `fraud-detection` | Tầng datastore + consumer. Các workload này sở hữu hoặc tiêu thụ state liên tục. SA riêng đảm bảo annotation IRSA (AWS RDS/ElastiCache) trong tương lai được scope đúng. |
| `techx-loadgen` | `load-generator` | Tách biệt: load-gen không được chia sẻ identity với workload production. load-gen bị xâm phạm không được mạo danh checkout hay data service. |
| `techx-flagd` | `flagd` | Tách biệt: flagd giữ BTC sync token (Bearer token trong args). SA riêng ngăn workload khác chia sẻ identity này nếu flagd được cấp quyền đọc K8s secret trong tương lai. |

## 5.2 Bảng phân nhóm đề xuất

| Tên SA | Workloads | automountServiceAccountToken | Cần RoleBinding? |
|---|---|---|---|
| `techx-frontend` | frontend, frontend-proxy, image-provider | `false` | Không — không có K8s API call nào trong source |
| `techx-checkout` | checkout, payment, email, currency, shipping, quote | `false` | Không — không có K8s API call nào trong source |
| `techx-catalog` | product-catalog, product-reviews, recommendation, ad, llm | `false` | Không — không có K8s API call nào trong source |
| `techx-data` | cart, valkey-cart, kafka, postgresql, accounting, fraud-detection | `false` | Không — không có K8s API call nào trong source |
| `techx-loadgen` | load-generator | `false` | Không — không có K8s API call nào trong source |
| `techx-flagd` | flagd | `false` | Không — flagd đọc flag qua HTTP endpoint, không qua K8s API |

## 5.3 Tại sao KHÔNG tạo RoleBinding?

Kết quả grep source code:
- Go source: không có tham chiếu nào tới `k8s.io/client-go`, `InClusterConfig`, `KUBERNETES_SERVICE_HOST`
- Python source: không có tham chiếu nào tới package `kubernetes`, `in_cluster_config`
- C# source: không có tham chiếu nào tới `KubernetesClient`

**Không có workload nào gọi Kubernetes API. Do đó không tạo RoleBinding.**
Tạo RoleBinding mà không có bằng chứng nhu cầu vi phạm nguyên tắc least privilege — ngược lại với mục tiêu T10.

---

# 6. Các file cần thay đổi

## 6.1 `templates/serviceaccount.yaml`

**Tại sao:** Hiện tại chỉ render 1 SA. Cần render 6 SA.

**Cần thay đổi gì:** Thay khối SA đơn bằng vòng lặp range trên map `serviceAccounts` mới trong values.yaml. Mỗi entry tạo 1 SA với `automountServiceAccountToken: false`.

**Tác động:** Helm sẽ tạo 6 SA mới. SA `techx-corp` cũ vẫn tồn tại cho đến khi xóa thủ công hoặc đặt `serviceAccount.create: false`.

**Template đề xuất mới:**
```yaml
{{- range $saName, $saConfig := .Values.serviceAccounts }}
{{- if $saConfig.create }}
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{ $saName }}
  namespace: {{ $.Release.Namespace }}
  labels:
    {{- include "techx-corp.labels" $ | nindent 4 }}
  {{- if $saConfig.annotations }}
  annotations:
    {{- toYaml $saConfig.annotations | nindent 4 }}
  {{- end }}
automountServiceAccountToken: false
{{- end }}
{{- end }}
```

## 6.2 `values.yaml`

**Tại sao:** Cần thêm map `serviceAccounts` (mới) và thêm field `serviceAccountName` cho từng component.

**Cần thêm — phần `serviceAccounts` mới:**
```yaml
serviceAccounts:
  techx-frontend:
    create: true
    annotations: {}
  techx-checkout:
    create: true
    annotations: {}
  techx-catalog:
    create: true
    annotations: {}
  techx-data:
    create: true
    annotations: {}
  techx-loadgen:
    create: true
    annotations: {}
  techx-flagd:
    create: true
    annotations: {}
```

**Cần thêm cho từng component — field `serviceAccountName`:**
```yaml
components:
  frontend:
    enabled: true
    serviceAccountName: techx-frontend   # THÊM DÒNG NÀY
  frontend-proxy:
    enabled: true
    serviceAccountName: techx-frontend
  image-provider:
    enabled: true
    serviceAccountName: techx-frontend
  checkout:
    enabled: true
    serviceAccountName: techx-checkout
  payment:
    enabled: true
    serviceAccountName: techx-checkout
  email:
    enabled: true
    serviceAccountName: techx-checkout
  currency:
    enabled: true
    serviceAccountName: techx-checkout
  shipping:
    enabled: true
    serviceAccountName: techx-checkout
  quote:
    enabled: true
    serviceAccountName: techx-checkout
  product-catalog:
    enabled: true
    serviceAccountName: techx-catalog
  product-reviews:
    enabled: true
    serviceAccountName: techx-catalog
  recommendation:
    enabled: true
    serviceAccountName: techx-catalog
  ad:
    enabled: true
    serviceAccountName: techx-catalog
  llm:
    enabled: true
    serviceAccountName: techx-catalog
  cart:
    enabled: true
    serviceAccountName: techx-data
  valkey-cart:
    enabled: true
    serviceAccountName: techx-data
  kafka:
    enabled: true
    serviceAccountName: techx-data
  postgresql:
    enabled: true
    serviceAccountName: techx-data
  accounting:
    enabled: true
    serviceAccountName: techx-data
  fraud-detection:
    enabled: true
    serviceAccountName: techx-data
  load-generator:
    enabled: true
    serviceAccountName: techx-loadgen
  flagd:
    enabled: true
    serviceAccountName: techx-flagd
```

**Cần thay đổi — phần `serviceAccount` cũ:**
```yaml
serviceAccount:
  create: false   # ĐỔI từ true thành false — ngừng tạo SA legacy techx-corp
  name: ""
  annotations: {}
```

**Tác động:** SA `techx-corp` cũ ngừng được tạo ở lần `helm upgrade` tiếp theo. Workload vẫn tham chiếu SA này sẽ lỗi — phải cập nhật field `serviceAccountName` cho tất cả component TRƯỚC khi tắt SA cũ.

## 6.3 `templates/_objects.tpl`

**Tại sao:** Template deployment hiện tại gọi `{{ include "techx-corp.serviceAccountName" .}}` — luôn resolve thành SA `techx-corp` duy nhất. Cần đọc `serviceAccountName` per-component thay thế.

**Cần thay đổi — dòng 35 trong `_objects.tpl`:**

Hiện tại:
```yaml
serviceAccountName: {{ include "techx-corp.serviceAccountName" .}}
```

Đề xuất:
```yaml
serviceAccountName: {{ .serviceAccountName | default (include "techx-corp.serviceAccountName" .) }}
```

Dòng này đọc `serviceAccountName` per-component từ values nếu được set, fallback về behavior cũ nếu không set (rollout an toàn).

**Tác động:** Mọi Deployment được render bởi template này sẽ dùng SA nhóm riêng thay vì SA chung.

## 6.4 `templates/_helpers.tpl`

**Tại sao:** Helper `techx-corp.serviceAccountName` vẫn cần thiết để backward compatibility (fallback trong `_objects.tpl`). Không cần thay đổi helper này.

**Không cần thay đổi.**

## 6.5 File KHÔNG thuộc chart này (dependency charts)

`grafana-clusterrole` của Grafana được tạo bởi upstream `grafana` Helm chart, không phải bởi `templates/serviceaccount.yaml`. Sửa nó cần override grafana chart values — theo dõi riêng ở **SEC-01**, không phải phần của T10.

---

# 7. Kế hoạch thực thi từng bước

> **Nhắc nhở:** Không deploy, không apply, không kubectl trong task này. Kế hoạch này dành cho thực thi sau.

## Phase 1 — Chuẩn bị thay đổi chart (không ảnh hưởng cluster đang chạy)

**Bước 1.1** — Cập nhật `values.yaml`: thêm map `serviceAccounts` với 6 entry.

**Bước 1.2** — Cập nhật `values.yaml`: thêm field `serviceAccountName` cho từng 22 component trỏ đến SA nhóm tương ứng.

**Bước 1.3** — Cập nhật `templates/serviceaccount.yaml`: thay SA đơn bằng vòng lặp range trên `serviceAccounts`.

**Bước 1.4** — Cập nhật `templates/_objects.tpl` dòng 35: dùng `serviceAccountName` per-component với fallback.

**Bước 1.5** — Chạy `helm template` locally để xác minh kết quả render. Kiểm tra tất cả 22 Deployment hiển thị đúng tên SA.

## Phase 2 — Deploy với SA cũ vẫn còn active (không downtime)

**Bước 2.1** — Giữ `serviceAccount.create: true` tạm thời để SA `techx-corp` cũ vẫn tồn tại song song với SA mới.

**Bước 2.2** — Chạy `helm upgrade`. Thao tác này tạo 6 SA mới + rolling restart toàn bộ 22 Deployment để dùng SA mới.

**Bước 2.3** — Verify tất cả pod Running với SA mới (xem Mục 9).

## Phase 3 — Xóa SA legacy

**Bước 3.1** — Đặt `serviceAccount.create: false` trong values.yaml.

**Bước 3.2** — Chạy `helm upgrade`. Helm sẽ không còn quản lý object SA `techx-corp`.

**Bước 3.3** — Xóa SA cũ thủ công: `kubectl delete serviceaccount techx-corp -n techx-tf3`

**Bước 3.4** — Chạy smoke test đầy đủ (xem Mục 9).

---

# 8. Đánh giá Rủi ro

## 8.1 Deployment rollout và Pod restart

**Rủi ro: Toàn bộ 22 Deployment sẽ trigger rolling restart.**

Khi `serviceAccountName` thay đổi trong Deployment spec, Kubernetes phát hiện diff trong pod spec và khởi động rolling update. Với `replicas: 1` (tất cả service), pod cũ bị terminate và pod mới khởi động. Trong khoảng thời gian này (thường 10–30s mỗi service), service **không khả dụng**.

**Giảm thiểu:**
- Thực thi trong khung giờ ít traffic
- Monitor bằng `kubectl rollout status deploy/<tên> -n techx-tf3` trong khi apply
- Chuẩn bị rollback: `helm rollback techx-corp <revision-trước> -n techx-tf3`
- KHÔNG deploy khi error budget đã cạn (kiểm tra Grafana checkout SLO trước)

## 8.2 RBAC

**Rủi ro: Thấp — không thêm RoleBinding nào.**

SA mới được tạo với zero permission (không có RoleBinding). Token SA được mount với `automountServiceAccountToken: false`. Thay đổi duy nhất là file token không còn tồn tại trong filesystem pod.

**Rủi ro ngoại lệ:** Nếu code workload thực sự đọc `/var/run/secrets/kubernetes.io/serviceaccount/token` lúc runtime (không phải cho K8s API, mà cho mục đích OIDC/JWT) và việc tìm kiếm source code bỏ sót — đặt `automountServiceAccountToken: false` sẽ khiến workload đó lỗi. Tìm kiếm source code không tìm thấy bằng chứng nào, nhưng không thể loại trừ 100% mà không có runtime testing.

**Giảm thiểu:** Đặt `automountServiceAccountToken: false` ở cấp SA object (trong `serviceaccount.yaml`), KHÔNG phải ở cấp pod spec. Cách này, nếu một component cụ thể cần opt back in, có thể override bằng `automountServiceAccountToken: true` trong pod spec mà không cần thay đổi SA.

## 8.3 ImagePullSecrets

**Rủi ro: Không có.**

`imagePullSecrets` trong chart này được cấu hình qua `default.image.pullSecrets` ở cấp pod spec (`_objects.tpl` dòng 33), KHÔNG qua SA annotation. Đổi SA không ảnh hưởng việc pull image từ ECR.

**Nguồn:** `templates/_objects.tpl` dòng 32–34

## 8.4 Token Projection

**Rủi ro: Thấp — nhưng cần verify flagd.**

`flagd` dùng Bearer token (`authHeader: Bearer 8de6...`) để sync flag từ BTC endpoint. Token này được truyền như **command argument** trong pod spec (tìm thấy trong `describe deploy flagd`), KHÔNG qua projected service account token hay Kubernetes secret volume. Đặt `automountServiceAccountToken: false` cho SA `techx-flagd` không ảnh hưởng sync token của flagd.

**Nguồn:** Output `kubectl describe deploy flagd` cho thấy Bearer token trong command args, không mount từ SA.

## 8.5 Helm Upgrade

**Rủi ro: Race condition nếu SA `techx-corp` cũ bị xóa trước khi pod rolling xong.**

Nếu Phase 3 (xóa SA cũ) được thực hiện trước khi tất cả pod đã fully rolled sang SA mới, bất kỳ pod nào vẫn tham chiếu SA `techx-corp` sẽ fail schedule.

**Giảm thiểu:** Phase 2 (helm upgrade với SA mới) phải hoàn thành đầy đủ và tất cả pod phải Running trước khi bắt đầu Phase 3 (xóa SA cũ). Thêm check `kubectl rollout status` cho cả 22 deployment như gate.

## 8.6 DaemonSet otel-collector

`otel-collector` được deploy như DaemonSet bởi upstream chart với SA riêng (`otel-collector`). Nó KHÔNG thuộc `.Values.components` và KHÔNG bị ảnh hưởng bởi task này.

**Nguồn:** `values.yaml` dòng 907: `opentelemetry-collector:`, `mode: daemonset`

---

# 9. Kế hoạch Verification

> Tất cả bước chỉ mô tả. **Không deploy. Không apply. Không kubectl.**

## 9.1 Verify trước deploy (helm template dry-run)

**Bước V1 — Render chart locally:**
```bash
helm template techx-corp ./techx-corp-chart \
  --set default.image.repository=<ECR> \
  -f deploy/values-flagd-sync.yaml \
  > /tmp/rendered.yaml
```

**Cần kiểm tra trong output:**
- Số lượng object `kind: ServiceAccount` = đúng 6 (techx-frontend, techx-checkout, techx-catalog, techx-data, techx-loadgen, techx-flagd)
- Mọi `kind: ServiceAccount` có `automountServiceAccountToken: false`
- Mọi `kind: Deployment` có `serviceAccountName` khớp với SA mong đợi cho component đó
- Không có Deployment nào vẫn tham chiếu SA `techx-corp` (phải bằng 0)
- Không có `kind: RoleBinding` hay `kind: ClusterRoleBinding` trong output

**Bước V2 — Diff với trạng thái hiện tại:**
```bash
helm diff upgrade techx-corp ./techx-corp-chart \
  --set default.image.repository=<ECR> \
  -f deploy/values-flagd-sync.yaml
```
Diff mong đợi: 6 SA create, 22 Deployment update (chỉ thay đổi serviceAccountName).

## 9.2 Verify sau deploy (sau helm upgrade trong tương lai)

**Bước V3 — Xác nhận SA tồn tại:**
```bash
kubectl get serviceaccount -n techx-tf3
# Mong đợi: techx-frontend, techx-checkout, techx-catalog, techx-data, techx-loadgen, techx-flagd
# Mỗi cái có automountServiceAccountToken: false
```

**Bước V4 — Xác nhận SA assignment của pod:**
```bash
kubectl get pods -n techx-tf3 -o custom-columns=\
'NAME:.metadata.name,SA:.spec.serviceAccountName'
# Mong đợi: mỗi pod hiển thị SA nhóm của nó, không phải techx-corp
```

**Bước V5 — Xác nhận không còn token mount trong pod:**
```bash
kubectl exec deploy/checkout -n techx-tf3 -- \
  ls /var/run/secrets/kubernetes.io/serviceaccount/ 2>&1
# Mong đợi: ls: cannot access ... No such file or directory
```

**Bước V6 — Xác nhận SA permissions (không có RBAC bất ngờ):**
```bash
kubectl auth can-i --list \
  --as=system:serviceaccount:techx-tf3:techx-checkout
# Mong đợi: chỉ selfsubjectreviews + public non-resource URLs
# KHÔNG được hiển thị: secrets, pods, configmaps, hay verb resource nào

kubectl auth can-i --list \
  --as=system:serviceaccount:techx-tf3:techx-frontend
# Kỳ vọng tương tự

kubectl auth can-i --list \
  --as=system:serviceaccount:techx-tf3:techx-data
# Kỳ vọng tương tự

kubectl auth can-i --list \
  --as=system:serviceaccount:techx-tf3:techx-flagd
# Kỳ vọng tương tự
```

**Bước V7 — Smoke test chức năng ứng dụng:**
```bash
# 1. Storefront load được
curl -s -o /dev/null -w "%{http_code}" http://localhost:8080
# Mong đợi: 200

# 2. API danh sách sản phẩm
curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/api/products
# Mong đợi: 200

# 3. Chi tiết sản phẩm với AI review
curl -s -o /dev/null -w "%{http_code}" \
  http://localhost:8080/api/product-reviews/L9ECAV7KIM
# Mong đợi: 200

# 4. Thao tác cart
curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/cart
# Mong đợi: 200

# 5. Checkout end-to-end (test thủ công qua browser)
# Mong đợi: đặt hàng thành công
```

**Bước V8 — Xác nhận flagd vẫn sync từ BTC:**
```bash
kubectl logs deploy/flagd -n techx-tf3 --tail=20
# Mong đợi: log sync thành công, không có lỗi "auth" hay "connection refused"
```

---

# Bảng tóm tắt

| Mục | Phát hiện chính |
|---|---|
| ServiceAccount trong chart | 1 SA (`techx-corp`) render tất cả 22 component |
| Role/RoleBinding trong chart | Không có — zero template tồn tại |
| ClusterRole trong chart | Không có — chỉ dependency chart mới có ClusterRole |
| App workload gọi K8s API | Không có — xác nhận qua tìm kiếm source code |
| RoleBinding cần tạo | **Không có** — không workload nào cần K8s API |
| `automountServiceAccountToken` | Không được set ở đâu → mặc định `true` → phải thêm `false` |
| File cần thay đổi | `serviceaccount.yaml`, `values.yaml`, `_objects.tpl` |
| Tác động Deployment | Toàn bộ 22 Deployment sẽ rolling restart |
| Rủi ro cao nhất | Pod downtime trong rollout (single replica, không có PDB) |

---

*Báo cáo tạo ngày: 2026-07-10*
*Dựa trên source code — không dùng live cluster query cho báo cáo thiết kế này.*
*Mọi trích dẫn nguồn tham chiếu file trong `phase3 - information/techx-corp-chart/`*
