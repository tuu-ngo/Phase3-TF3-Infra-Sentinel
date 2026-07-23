# Đánh giá Bảo mật — RBAC & Lộ Token ServiceAccount

## Người phụ trách
CDO01

## Thông tin đánh giá

| Trường | Giá trị |
|---|---|
| Ngày đánh giá | 2026-07-09 |
| Cập nhật lần cuối | 2026-07-16 |
| Cluster | techx-corp-tf3 |
| Region | ap-southeast-1 |
| Namespace | techx-tf3 |
| Người thực hiện | CDO01 |
| Phương pháp | Liệt kê live cluster qua `kubectl auth can-i`, đọc RBAC manifest trực tiếp |

---

## Tóm tắt điều hành

| Mức độ | Số lượng |
|---|---|
| CAO (HIGH) | 1 |
| TRUNG BÌNH (MEDIUM) | 1 |
| THÔNG TIN (INFO) | 1 |

Không phát hiện xâm phạm đang hoạt động. Tuy nhiên, hai cấu hình sai vi phạm nguyên tắc
least privilege và có thể làm tăng đáng kể blast radius nếu bất kỳ workload nào bị compromise.
Cả hai đều chỉ cần thay đổi YAML và `helm upgrade` — ước tính effort dưới 1 ngày, chi phí gần bằng 0.

**Mức giảm rủi ro dự kiến sau khi sửa: Cao**

---

## Phạm vi đánh giá

Liệt kê toàn bộ ServiceAccount, Role, ClusterRole, RoleBinding, ClusterRoleBinding trong
namespace `techx-tf3` và toàn cluster. Xác minh quyền thực tế bằng impersonation `kubectl auth can-i`.
Kiểm tra cài đặt `automountServiceAccountToken` trên toàn bộ 25 deployment.

---

## Các lệnh đã chạy (kèm kết quả thực tế)

### Bước 1 — Liệt kê ServiceAccount trong namespace

```bash
$ kubectl -n techx-tf3 get serviceaccount -o wide

NAME             SECRETS   AGE
default          0         39h
grafana          0         39h
jaeger           0         39h
otel-collector   0         39h
prometheus       0         39h
techx-corp       0         39h
```

**Nhận xét:** Có 6 SA trong namespace. `techx-corp` là SA dùng chung cho toàn bộ 22 business service.
Grafana, jaeger, otel-collector, prometheus là SA của dependency chart (upstream managed).

---

### Bước 2 — Liệt kê ClusterRole liên quan

```bash
$ kubectl get clusterrole | grep -E "techx|grafana|jaeger|otel|prometheus"

grafana-clusterrole      2026-07-07T12:46:23Z
otel-collector           2026-07-07T12:46:23Z
prometheus               2026-07-07T12:46:24Z
```

**Nhận xét:** `grafana-clusterrole` là ClusterRole — áp dụng toàn cluster, không giới hạn namespace.

---

### Bước 3 — Đọc nội dung grafana-clusterrole

```bash
$ kubectl get clusterrole grafana-clusterrole -o yaml

apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: grafana-clusterrole
  # (labels, annotations bị bỏ cho gọn)
rules:
- apiGroups:
  - ""
  resources:
  - configmaps
  - secrets          # ← ĐÂY LÀ VẤN ĐỀ: đọc secrets toàn cluster
  verbs:
  - get
  - watch
  - list
```

**Nhận xét:** Rule này grant quyền `get/watch/list` lên resource `secrets` — không giới hạn namespace
→ Grafana SA có thể đọc **mọi secret trong toàn cluster**, kể cả `kube-system`.

---

### Bước 4 — Kiểm tra ClusterRoleBinding

```bash
$ kubectl -n techx-tf3 get clusterrolebinding | grep grafana

grafana-clusterrolebinding   ClusterRole/grafana-clusterrole   39h
  techx-tf3/grafana
```

**Nhận xét:** SA `grafana` trong namespace `techx-tf3` được bind với ClusterRole cluster-wide.

---

### Bước 5 — Xác minh quyền thực tế (PoC sống)

```bash
# Grafana SA có đọc được secrets không?
$ kubectl auth can-i get secrets \
    --as=system:serviceaccount:techx-tf3:grafana
yes   # ← xác nhận CÓ quyền

# Có list secrets không?
$ kubectl auth can-i list secrets \
    --as=system:serviceaccount:techx-tf3:grafana
yes   # ← xác nhận CÓ quyền

# Có đọc secrets ở namespace kube-system không?
$ kubectl auth can-i list secrets \
    --as=system:serviceaccount:techx-tf3:grafana \
    -n kube-system
yes   # ← NGUY HIỂM: có thể đọc cả kube-system
```

---

### Bước 6 — Liệt kê secrets bị ảnh hưởng (tên, không lấy giá trị)

```bash
$ kubectl get secrets --all-namespaces --no-headers

kube-system   aws-load-balancer-tls                    kubernetes.io/tls
kube-system   sh.helm.release.v1.aws-lb.v1             helm.sh/release.v1
kube-system   sh.helm.release.v1.metrics-server.v1     helm.sh/release.v1
techx-tf3     grafana                                  Opaque
techx-tf3     sh.helm.release.v1.techx-corp.v1         helm.sh/release.v1
techx-tf3     sh.helm.release.v1.techx-corp.v2         helm.sh/release.v1
techx-tf3     sh.helm.release.v1.techx-corp.v3         helm.sh/release.v1
techx-tf3     sh.helm.release.v1.techx-corp.v4         helm.sh/release.v1
techx-tf3     sh.helm.release.v1.techx-corp.v5         helm.sh/release.v1
techx-tf3     sh.helm.release.v1.techx-corp.v6         helm.sh/release.v1
techx-tf3     sh.helm.release.v1.techx-corp.v7         helm.sh/release.v1
```

**Tổng cộng: 11 secrets** — Grafana SA đọc được tất cả.

---

### Bước 7 — Kiểm tra key trong grafana secret

```bash
$ kubectl -n techx-tf3 get secret grafana -o json \
    | python -c "import json,sys; d=json.load(sys.stdin); \
      print('Keys:', list(d['data'].keys()))"

Keys: ['admin-password', 'admin-user', 'ldap-toml']
```

**Nhận xét:** Secret Grafana chứa admin-password và admin-user — đây là credentials đăng nhập vào Grafana UI.

---

### Bước 8 — Audit automountServiceAccountToken trên toàn bộ deployment

```bash
$ kubectl -n techx-tf3 get deploy -o json | python -c "
import json, sys
data = json.load(sys.stdin)
print(f'{'DEPLOY':<30} {'AUTOMOUNT_SPEC':<25} {'SA':<20}')
print('-'*75)
for d in data['items']:
    name = d['metadata']['name']
    spec = d['spec']['template']['spec']
    automount = spec.get('automountServiceAccountToken', 'NOT SET (mặc định True)')
    sa = spec.get('serviceAccountName', 'default')
    print(f'{name:<30} {str(automount):<25} {sa:<20}')
"

DEPLOY                         AUTOMOUNT_SPEC            SA
---------------------------------------------------------------------------
accounting                     NOT SET (mặc định True)   techx-corp
ad                             NOT SET (mặc định True)   techx-corp
cart                           NOT SET (mặc định True)   techx-corp
checkout                       NOT SET (mặc định True)   techx-corp
currency                       NOT SET (mặc định True)   techx-corp
email                          NOT SET (mặc định True)   techx-corp
flagd                          NOT SET (mặc định True)   techx-corp
fraud-detection                NOT SET (mặc định True)   techx-corp
frontend                       NOT SET (mặc định True)   techx-corp
frontend-proxy                 NOT SET (mặc định True)   techx-corp
image-provider                 NOT SET (mặc định True)   techx-corp
kafka                          NOT SET (mặc định True)   techx-corp
llm                            NOT SET (mặc định True)   techx-corp
load-generator                 NOT SET (mặc định True)   techx-corp
payment                        NOT SET (mặc định True)   techx-corp
postgresql                     NOT SET (mặc định True)   techx-corp
product-catalog                NOT SET (mặc định True)   techx-corp
product-reviews                NOT SET (mặc định True)   techx-corp
quote                          NOT SET (mặc định True)   techx-corp
recommendation                 NOT SET (mặc định True)   techx-corp
shipping                       NOT SET (mặc định True)   techx-corp
valkey-cart                    NOT SET (mặc định True)   techx-corp
grafana                        True                      grafana
```

---

### Bước 9 — Kiểm tra quyền của SA techx-corp

```bash
$ kubectl auth can-i --list \
    --as=system:serviceaccount:techx-tf3:techx-corp

Resources                                       Non-Resource URLs    Verbs
selfsubjectreviews.authentication.k8s.io        []                   [create]
selfsubjectaccessreviews.authorization.k8s.io   []                   [create]
                                                [/healthz]           [get]
                                                [/version]           [get]
                                                [/api/*]             [get]
# ... (các public non-resource URL khác)
# KHÔNG có quyền gì với Kubernetes resources
```

**Nhận xét:** SA `techx-corp` hiện không có quyền với bất kỳ K8s resource nào. Token tồn tại nhưng chưa nguy hiểm ngày hôm nay.


---

## Tóm tắt phát hiện

**Kỳ vọng:**
- `grafana-clusterrole` chỉ cho phép đọc secret trong namespace `techx-tf3`
- Business pod không mount SA token nếu không có lý do gọi Kubernetes API

**Thực tế quan sát:**
- `grafana-clusterrole` là **ClusterRole** — cấp quyền `get/list/watch` lên `secrets` toàn cluster, kể cả `kube-system`
- **22/25 business deployment** đang mount token SA `techx-corp` theo mặc định, không có `automountServiceAccountToken: false`

---

## FINDING-01 — Grafana ServiceAccount có thể đọc Secrets toàn cluster

**Tiêu đề:** Grafana ServiceAccount đọc được Secrets trên toàn cluster (cluster-wide)

**Mức độ:** CAO (HIGH)

**Lý do mức độ cao:**
- Phạm vi quyền: Toàn cluster (không giới hạn namespace)
- Tài nguyên nhạy cảm: `secrets` — chứa credentials, TLS certificate, Helm release values
- Độ phức tạp khai thác: Thấp — chỉ cần có token SA của Grafana pod là đủ
- Hậu quả: Lộ credentials và nguy cơ chiếm quyền cluster

**CWE:** CWE-269: Improper Privilege Management

**Mô tả:**

ServiceAccount `grafana` (namespace `techx-tf3`) được bind với ClusterRole `grafana-clusterrole`
thông qua ClusterRoleBinding. ClusterRole này cấp quyền `get`, `watch`, `list` lên resource `secrets`
trên **toàn bộ cluster**, không giới hạn namespace. Đây là hành vi mặc định của upstream Grafana
Helm chart và không được override khi deploy.

---

### Bằng chứng (đã verify trên live cluster)

**ClusterRole rule thực tế:**
```yaml
rules:
- apiGroups: [""]
  resources:
  - configmaps
  - secrets          # ← grant đọc secrets toàn cluster
  verbs: [get, watch, list]
```

**Xác minh quyền thực tế bằng impersonation:**
```bash
$ kubectl auth can-i get secrets \
    --as=system:serviceaccount:techx-tf3:grafana
yes

$ kubectl auth can-i list secrets \
    --as=system:serviceaccount:techx-tf3:grafana
yes

$ kubectl auth can-i list secrets \
    --as=system:serviceaccount:techx-tf3:grafana \
    -n kube-system
yes   # ← đọc được cả kube-system
```

---

### Danh sách secrets bị ảnh hưởng (11 secrets, chỉ ghi tên)

| Namespace | Tên Secret | Loại | Mức độ nhạy cảm |
|---|---|---|---|
| `kube-system` | `aws-load-balancer-tls` | `kubernetes.io/tls` | TLS private key của Load Balancer |
| `kube-system` | `sh.helm.release.v1.aws-lb.v1` | `helm.sh/release.v1` | Config LB |
| `kube-system` | `sh.helm.release.v1.metrics-server.v1` | `helm.sh/release.v1` | Config metrics-server |
| `techx-tf3` | `grafana` | `Opaque` | `admin-password`, `admin-user`, `ldap-toml` |
| `techx-tf3` | `sh.helm.release.v1.techx-corp.v1~v7` | `helm.sh/release.v1` | **Toàn bộ Helm values qua 7 revision, có thể chứa flagd sync token** |

Helm release secrets được mã hóa base64+gzip nhưng **giải mã rất dễ dàng**. Kẻ tấn công có token SA
Grafana có thể đọc cả 7 revision để tái tạo toàn bộ cấu hình deploy, bao gồm mọi secret truyền
vào qua `-f values-flagd-sync.yaml`.

---

### Luồng tấn công chi tiết

```
┌─────────────────────────────────────────────────────────────────────┐
│  BƯỚC 1 — Xâm nhập vào Grafana pod                                 │
│                                                                     │
│  Phương thức có thể dùng:                                           │
│  • CVE-2021-43798: Grafana path traversal                          │
│    GET /public/plugins/alertmanager/../../../../../etc/passwd       │
│  • Grafana datasource SSRF: dùng datasource để gọi internal API    │
│  • Plugin độc hại được cài vào Grafana                              │
│  • XSS dẫn đến chiếm session admin                                 │
└──────────────────────────┬──────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────────┐
│  BƯỚC 2 — Lấy Service Account Token                                 │
│                                                                     │
│  Sau khi có shell trong pod:                                        │
│  $ cat /var/run/secrets/kubernetes.io/serviceaccount/token          │
│  eyJhbGciOiJSUzI1NiIsImtpZCI6IjM2...   ← JWT token hợp lệ          │
│                                                                     │
│  Token này là JWT được ký bởi Kubernetes, có hạn dài                │
│  (thường 1 năm với projected token, hoặc không hết hạn với static)  │
└──────────────────────────┬──────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────────┐
│  BƯỚC 3 — Authenticate với Kubernetes API từ máy kẻ tấn công       │
│                                                                     │
│  $ TOKEN=$(cat stolen_token.txt)                                    │
│  $ curl -k https://<K8S_API>:443/api/v1/namespaces \               │
│      -H "Authorization: Bearer $TOKEN"                              │
│                                                                     │
│  → Kubernetes API xác nhận token hợp lệ, trả về danh sách          │
└──────────────────────────┬──────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────────┐
│  BƯỚC 4 — Liệt kê và đọc secrets                                   │
│                                                                     │
│  # Liệt kê tất cả secrets                                           │
│  $ curl -k https://<K8S_API>/api/v1/secrets \                       │
│      -H "Authorization: Bearer $TOKEN"                              │
│                                                                     │
│  # Đọc Helm release secret (chứa toàn bộ values deploy)            │
│  $ curl -k https://<K8S_API>/api/v1/namespaces/techx-tf3/ \        │
│      secrets/sh.helm.release.v1.techx-corp.v7 \                    │
│      -H "Authorization: Bearer $TOKEN"                              │
│                                                                     │
│  # Giải mã Helm release secret:                                     │
│  $ echo "<base64_data>" | base64 -d | gunzip                        │
│  → Lộ toàn bộ values.yaml bao gồm flagd sync token                  │
└──────────────────────────┬──────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────────┐
│  BƯỚC 5 — Khai thác flagd sync token (DISQUALIFY)                  │
│                                                                     │
│  Flagd sync token trong Helm values:                                │
│  authHeader: "Bearer 8de6246060a65f500bc44988467c5985b..."          │
│                                                                     │
│  → Kẻ tấn công có thể:                                              │
│    • Đọc flag configuration từ BTC endpoint                         │
│    • Hiểu được sự cố nào BTC đang chuẩn bị inject                   │
│    • Vô hiệu hóa cơ chế sự cố nếu có write access                  │
│                                                                     │
│  → RULES.md: vi phạm flagd mechanism = DISQUALIFY                   │
└──────────────────────────┬──────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────────┐
│  BƯỚC 6 — Lateral movement (nếu có thêm quyền)                     │
│                                                                     │
│  Với TLS key của ALB (aws-load-balancer-tls):                       │
│  → Giải mã traffic HTTPS của toàn bộ người dùng                     │
│                                                                     │
│  Với admin credentials của Grafana:                                 │
│  → Chiếm hoàn toàn Grafana, chỉnh sửa dashboard, tắt alert         │
└─────────────────────────────────────────────────────────────────────┘
```


### Tác động với SLO và Business

- **Checkout SLO ≥ 99%:** Nếu kẻ tấn công đọc được flagd sync token và inject flag làm checkout fail →
  SLO bị vi phạm trực tiếp, doanh thu bị ảnh hưởng
- **Grafana admin bị chiếm:** Mất khả năng quan sát trong incident — MTTR tăng, SLO vỡ kéo dài hơn
- **TLS key của ALB bị lộ:** Toàn bộ traffic HTTPS của user bị giải mã
- **DISQUALIFY risk:** Lộ flagd sync token = vi phạm RULES.md = cả TF3 bị loại khỏi vòng đánh giá

---

### Giải pháp cụ thể

#### Giải pháp 1 — Thay ClusterRole → namespaced Role (khuyến nghị, ưu tiên cao nhất)

**Tại sao:** Grafana chỉ cần đọc secret trong namespace `techx-tf3` của nó (để load datasource credentials).
Không có lý do kỹ thuật nào để Grafana đọc secret ở `kube-system` hay namespace khác.

**Bước 1 — Tạo Role thay thế (namespace-scoped):**
```yaml
# File: grafana-role-patch.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: grafana
  namespace: techx-tf3
rules:
- apiGroups: [""]
  resources: ["configmaps", "secrets"]
  verbs: ["get", "watch", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: grafana
  namespace: techx-tf3
subjects:
- kind: ServiceAccount
  name: grafana
  namespace: techx-tf3
roleRef:
  kind: Role
  name: grafana
  apiGroup: rbac.authorization.k8s.io
```

**Bước 2 — Override Helm values để ngăn chart tự tạo lại ClusterRole:**
```yaml
# Thêm vào values.yaml hoặc values-override.yaml
grafana:
  rbac:
    create: true
    namespaced: true      # ← key config: tắt ClusterRole, dùng Role namespace-scoped
    pspEnabled: false
```

**Bước 3 — Deploy:**
```bash
helm upgrade techx-corp ./techx-corp-chart \
  --set default.image.repository=<ECR> \
  -f deploy/values-flagd-sync.yaml \
  -f grafana-rbac-override.yaml \
  -n techx-tf3
```

**Bước 4 — Xóa ClusterRole và ClusterRoleBinding cũ:**
```bash
kubectl delete clusterrolebinding grafana-clusterrolebinding
kubectl delete clusterrole grafana-clusterrole
```

**Bước 5 — Verify sau khi fix:**
```bash
# Phải trả về "no" sau khi fix
$ kubectl auth can-i list secrets \
    --as=system:serviceaccount:techx-tf3:grafana \
    -n kube-system
no   # ← mong đợi

# Phải vẫn trả về "yes" trong chính namespace của Grafana
$ kubectl auth can-i list secrets \
    --as=system:serviceaccount:techx-tf3:grafana \
    -n techx-tf3
yes  # ← Grafana vẫn hoạt động bình thường

# Grafana UI vẫn load được dashboard
$ curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/grafana/
200  # ← mong đợi
```

**Rollback nếu Grafana lỗi:**
```bash
helm rollback techx-corp <REVISION_TRƯỚC> -n techx-tf3
# Verify
kubectl get clusterrole grafana-clusterrole  # phải xuất hiện lại
```

---

## FINDING-02 — Business Workload tự động mount Service Account Token

**Tiêu đề:** 22 business pod mount token SA không cần thiết

**Mức độ:** TRUNG BÌNH (MEDIUM)

**Lý do mức độ trung bình:**
- Khả năng khai thác: Cần xâm phạm pod trước (RCE, SSRF, container escape)
- Tác động hiện tại: Giới hạn — SA `techx-corp` không có quyền K8s resource hiện tại
- Rủi ro tương lai: Cao — bất kỳ RoleBinding nào được add vào SA `techx-corp` sẽ ngay lập tức
  ảnh hưởng tất cả 22 pod mà không cần cấu hình thêm
- Defense-in-depth: Token mount tạo attack surface không cần thiết

**CWE:** CWE-250: Execution with Unnecessary Privileges

**Mô tả:**

Toàn bộ 22 business deployment dùng SA `techx-corp` mà không đặt `automountServiceAccountToken: false`.
Kubernetes mặc định là `true` — mọi business pod đều có JWT token hợp lệ được mount sẵn tại
`/var/run/secrets/kubernetes.io/serviceaccount/token`. Không có service nào trong số 22 service
cần gọi Kubernetes API (xác nhận qua tìm kiếm source code Go/Python/C#).

---

### Bằng chứng (đã verify trên live cluster)

**Kết quả audit toàn bộ 22 deployment:**
```
DEPLOY               AUTOMOUNT_SPEC              SA
------------------------------------------------------------
accounting           NOT SET (mặc định True)     techx-corp
ad                   NOT SET (mặc định True)     techx-corp
cart                 NOT SET (mặc định True)     techx-corp
checkout             NOT SET (mặc định True)     techx-corp
currency             NOT SET (mặc định True)     techx-corp
email                NOT SET (mặc định True)     techx-corp
flagd                NOT SET (mặc định True)     techx-corp
fraud-detection      NOT SET (mặc định True)     techx-corp
frontend             NOT SET (mặc định True)     techx-corp
frontend-proxy       NOT SET (mặc định True)     techx-corp
image-provider       NOT SET (mặc định True)     techx-corp
kafka                NOT SET (mặc định True)     techx-corp
llm                  NOT SET (mặc định True)     techx-corp
load-generator       NOT SET (mặc định True)     techx-corp
payment              NOT SET (mặc định True)     techx-corp
postgresql           NOT SET (mặc định True)     techx-corp
product-catalog      NOT SET (mặc định True)     techx-corp
product-reviews      NOT SET (mặc định True)     techx-corp
quote                NOT SET (mặc định True)     techx-corp
recommendation       NOT SET (mặc định True)     techx-corp
shipping             NOT SET (mặc định True)     techx-corp
valkey-cart          NOT SET (mặc định True)     techx-corp
```

**Xác nhận SA techx-corp hiện chưa có quyền K8s resource:**
```bash
$ kubectl auth can-i --list \
    --as=system:serviceaccount:techx-tf3:techx-corp

Resources                                       Verbs
selfsubjectreviews.authentication.k8s.io        [create]
selfsubjectaccessreviews.authorization.k8s.io   [create]
# Chỉ có các public non-resource URL
# KHÔNG CÓ quyền gì với secrets, pods, configmaps, hay bất kỳ resource nào
```

---

### Luồng tấn công chi tiết

```
┌─────────────────────────────────────────────────────────────────────┐
│  BƯỚC 1 — Xâm nhập vào bất kỳ business pod nào                     │
│                                                                     │
│  Ví dụ: RCE trong llm service (xử lý text từ user, attack surface  │
│  rộng), hoặc SSRF trong product-catalog, hoặc dependency           │
│  vulnerability trong bất kỳ library nào của 22 service             │
└──────────────────────────┬──────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────────┐
│  BƯỚC 2 — Đọc token từ filesystem pod                               │
│                                                                     │
│  $ cat /var/run/secrets/kubernetes.io/serviceaccount/token          │
│  eyJhbGciOiJSUzI1NiIsImtpZCI6...  ← JWT của SA techx-corp          │
│                                                                     │
│  $ cat /var/run/secrets/kubernetes.io/serviceaccount/namespace      │
│  techx-tf3                                                          │
│                                                                     │
│  $ cat /var/run/secrets/kubernetes.io/serviceaccount/ca.crt         │
│  -----BEGIN CERTIFICATE-----  ← CA cert để verify API server        │
└──────────────────────────┬──────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────────┐
│  BƯỚC 3 — Authenticate và trinh sát cluster [NGÀY HÔM NAY]         │
│                                                                     │
│  # Gọi API bằng token (hữu ích cho trinh sát)                       │
│  $ curl -k https://kubernetes.default.svc/api/v1/namespaces \       │
│      -H "Authorization: Bearer $TOKEN"                              │
│                                                                     │
│  → Ngày hôm nay: SA techx-corp không có quyền resource              │
│  → Nhưng kẻ tấn công đã có foothold trong cluster                   │
└──────────────────────────┬──────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────────┐
│  BƯỚC 4 — Khai thác khi có RBAC drift [RỦI RO TƯƠNG LAI]           │
│                                                                     │
│  Ví dụ: developer thêm RoleBinding cho techx-corp SA để debug:      │
│  kubectl create rolebinding debug-binding \                          │
│    --clusterrole=view \                                              │
│    --serviceaccount=techx-tf3:techx-corp                            │
│                                                                     │
│  → Ngay lập tức: tất cả 22 pod đều có quyền "view" toàn namespace   │
│  → Kẻ tấn công đang giữ token techx-corp (từ bước 2) có thể:        │
│    • Đọc toàn bộ ConfigMap (có thể chứa config nhạy cảm)            │
│    • Liệt kê pod, service, secret names                             │
│    • Leo thang thêm nếu "view" role có thêm quyền                   │
└──────────────────────────┬──────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────────┐
│  BƯỚC 5 — Lateral movement trong cluster                            │
│                                                                     │
│  Với token hợp lệ + quyền từ RBAC drift:                            │
│  → Enumerate pod của các service khác                               │
│  → Đọc ConfigMap chứa DB connection string                          │
│  → Tìm cách escalate đến cluster-admin                              │
└─────────────────────────────────────────────────────────────────────┘
```

**Tác động hiện tại:** Không có quyền K8s resource trực tiếp qua token này ngày hôm nay.

**Tác động tiềm năng:** Mọi RoleBinding được thêm vào SA `techx-corp` trong tương lai —
dù cố ý (developer thêm K8s API access cho feature mới) hay vô tình (copy-paste từ template) —
sẽ ngay lập tức ảnh hưởng tất cả 22 pod vì token đã mount sẵn. RBAC drift kiểu này phổ biến
trong cluster tồn tại lâu.

---

### Giải pháp cụ thể

#### Giải pháp — Tắt automount token trên toàn bộ SA (phương án tốt nhất)

**Phương án A — Tắt tại cấp ServiceAccount object:**
```yaml
# Sửa trong templates/serviceaccount.yaml của Helm chart
apiVersion: v1
kind: ServiceAccount
metadata:
  name: techx-corp
  namespace: techx-tf3
automountServiceAccountToken: false   # ← THÊM DÒNG NÀY
```

Khi set tại SA object, tất cả pod dùng SA đó đều không mount token nữa,
trừ khi pod spec tự override bằng `automountServiceAccountToken: true`.

**Phương án B — Tắt tại cấp pod spec (linh hoạt hơn):**
```yaml
# Trong values.yaml, thêm vào default section hoặc từng component
default:
  # ...
  podSpec:
    automountServiceAccountToken: false   # ← apply cho tất cả component
```

Hoặc trong `_objects.tpl`:
```yaml
spec:
  automountServiceAccountToken: {{ .automountServiceAccountToken | default false }}
```

**Deploy:**
```bash
helm upgrade techx-corp ./techx-corp-chart \
  --set default.image.repository=<ECR> \
  -f deploy/values-flagd-sync.yaml \
  -n techx-tf3
```

**Verify sau khi fix:**
```bash
# Kiểm tra token KHÔNG còn mount trong pod
$ kubectl -n techx-tf3 exec deploy/checkout -- \
    ls /var/run/secrets/kubernetes.io/serviceaccount/ 2>&1
ls: /var/run/secrets/kubernetes.io/serviceaccount/: No such file or directory
# ← mong đợi: không tìm thấy thư mục

# Kiểm tra một số pod quan trọng khác
$ kubectl -n techx-tf3 exec deploy/payment -- \
    ls /var/run/secrets/kubernetes.io/serviceaccount/ 2>&1
ls: cannot access...: No such file or directory

$ kubectl -n techx-tf3 exec deploy/product-catalog -- \
    ls /var/run/secrets/kubernetes.io/serviceaccount/ 2>&1
ls: cannot access...: No such file or directory

# Xác nhận ứng dụng vẫn chạy bình thường sau khi tắt token
$ curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/api/products
200   # ← storefront vẫn hoạt động

$ curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/cart
200   # ← cart vẫn hoạt động
```

**Rollback nếu có service lỗi:**
```bash
# Nếu 1 service specific bị lỗi, override tạm thời
kubectl -n techx-tf3 patch deployment <tên-service> \
  -p '{"spec":{"template":{"spec":{"automountServiceAccountToken":true}}}}'

# Hoặc rollback toàn bộ
helm rollback techx-corp <REVISION_TRƯỚC> -n techx-tf3
```

---

## FINDING-03 — Grafana Secret chứa Admin Credentials

**Tiêu đề:** Grafana secret chứa thông tin đăng nhập admin

**Mức độ:** THÔNG TIN (INFORMATIONAL)

**Mô tả:**
Secret `grafana` trong namespace `techx-tf3` chứa các key: `admin-user`, `admin-password`, `ldap-toml`.
Đây là credentials đăng nhập vào Grafana UI được tạo lúc `helm install`. Nếu mật khẩu mặc định
không được đổi sau deploy, Grafana admin có thể truy cập được qua `http://<host>:8080/grafana/`.

**Đặc biệt:** Theo phát hiện Finding-01, Grafana SA có thể đọc chính secret của mình →
kẻ tấn công compromise được Grafana pod có thể đọc admin-password, đăng nhập lại với quyền admin đầy đủ.

**Lưu ý:** Chỉ đọc key names — không lấy giá trị trong quá trình đánh giá.

**Lệnh kiểm tra:**
```bash
$ kubectl -n techx-tf3 get secret grafana -o json \
    | python -c "import json,sys; d=json.load(sys.stdin); \
      print('Keys in grafana secret:', list(d['data'].keys()))"

Keys in grafana secret: ['admin-password', 'admin-user', 'ldap-toml']
```

**Giải pháp:**
```bash
# 1. Đổi password Grafana admin ngay sau deploy
kubectl -n techx-tf3 exec deploy/grafana -- \
  grafana-cli admin reset-admin-password <NEW_STRONG_PASSWORD>

# 2. Hoặc đặt trong values.yaml (nhớ không commit giá trị thật)
grafana:
  adminPassword: "<PASSWORD_MẠNH>"  # ← dùng secret manager thay vì hardcode

# 3. Cân nhắc tắt anonymous access và yêu cầu auth thực sự
grafana:
  grafana.ini:
    auth.anonymous:
      enabled: false    # ← tắt anonymous access
```

---

## Đề xuất Backlog

| Mã | Phát hiện | Mức độ | Effort | Ưu tiên |
|---|---|---|---|---|
| SEC-01 | Đổi grafana ClusterRole → namespaced Role | CAO | XS | P1 |
| SEC-02 | Tắt SA token automount trên 22 business pod | TRUNG BÌNH | XS | P1 |
| SEC-03 | Verify và rotate Grafana admin credentials | THÔNG TIN | XS | P2 |

**XS = Extra Small** — cả ba đều chỉ là thay đổi YAML, không tốn thêm chi phí hạ tầng,
có thể deploy trong một lần `helm upgrade`.

---

### Chi tiết SEC-01

- **Việc cần làm:** Thay `grafana-clusterrole` (ClusterRole) + `grafana-clusterrolebinding`
  (ClusterRoleBinding) bằng `Role` + `RoleBinding` namespace-scoped trong `techx-tf3`
- **Tại sao làm ngay:** Phát hiện HIGH với blast radius xác nhận vào `kube-system` và Helm release secrets
  có thể chứa flagd sync token
- **Chi phí:** $0 — chỉ thay đổi YAML + helm upgrade
- **Rollback:** `helm rollback techx-corp <REVISION> -n techx-tf3`
- **Verify:** `kubectl auth can-i list secrets --as=system:serviceaccount:techx-tf3:grafana -n kube-system` → `no`
- **Verify Grafana vẫn chạy:** `curl http://localhost:8080/grafana/` → `200`

### Chi tiết SEC-02

- **Việc cần làm:** Thêm `automountServiceAccountToken: false` vào SA object `techx-corp`
  hoặc vào pod spec của 22 deployment
- **Tại sao làm ngay:** Defense-in-depth — ngăn token tồn tại trong pod filesystem.
  Chi phí không làm ngày càng tăng theo mỗi RoleBinding được thêm vào cluster
- **Chi phí:** $0 — 1 dòng YAML
- **Rollback:** Xóa flag, `helm upgrade`
- **Verify:** `kubectl exec deploy/checkout -- ls /var/run/secrets/...` → `No such file or directory`

---

## So sánh trước và sau khi fix

| Trạng thái | SEC-01 (Grafana ClusterRole) | SEC-02 (SA Token) |
|---|---|---|
| **Trước** | Grafana đọc được 11 secrets trên 2 namespace | 22 pod có JWT token trong filesystem |
| **Sau** | Grafana chỉ đọc được secret trong `techx-tf3` | Không pod nào có token SA trong filesystem |
| **Verify** | `auth can-i list secrets -n kube-system` → `no` | `exec -- ls /var/run/secrets/...` → Not found |
| **Rollback** | `helm rollback <revision>` | `helm rollback <revision>` |
| **Thời gian fix** | <30 phút | <30 phút |
| **Chi phí AWS** | $0 | $0 |

---

*Phân loại tài liệu: Nội bộ — Đánh giá Bảo mật TF3*
*Định dạng báo cáo: Kubernetes RBAC Security Assessment (theo chuẩn AWS Security Review / NCC Group)*
*Cập nhật: 2026-07-16*
