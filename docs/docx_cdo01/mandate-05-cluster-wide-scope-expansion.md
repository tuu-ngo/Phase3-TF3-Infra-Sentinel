# Mandate 5 — Mở rộng phạm vi 4 Kyverno policy ra toàn cluster (19/07/2026)

**Nguồn gốc:** tách từ mục 8 của `docs/docx_cdo01/mandate-05-gap-analysis-20260718.md` — user đặt lại câu hỏi phạm vi: 4 policy Mandate 5 hiện chỉ áp `namespaces: [techx-tf3]`, trong khi mandate nói "toàn bộ Task Force", không giới hạn 1 namespace. File này là bản cập nhật liên tục của câu hỏi đó — có gì đã sửa thật, có gì còn đang treo, ghi rõ ở đây thay vì phải lục lại cả cuộc điều tra gốc.

---

## 1. Câu hỏi gốc và phát hiện quyết định cả câu trả lời

Cluster có 6 namespace có pod: `techx-tf3`, `kube-system`, `kyverno`, `argocd`, `external-secrets`, `argo-rollouts` (90 pod, 139 container — quét toàn bộ 19/07).

**Phát hiện quan trọng nhất:** webhook `kyverno-resource-validating-webhook-cfg` đã có sẵn `namespaceSelector` loại trừ **`kube-system` và `kyverno`** ở tầng webhook:
```sh
kubectl get validatingwebhookconfigurations kyverno-resource-validating-webhook-cfg -o jsonpath='{.webhooks[0].namespaceSelector}'
```
```json
{"matchExpressions":[
  {"key":"kubernetes.io/metadata.name","operator":"NotIn","values":["kube-system"]},
  {"key":"kubernetes.io/metadata.name","operator":"NotIn","values":["kyverno"]}
]}
```
→ Request từ 2 namespace này **không bao giờ tới được Kyverno để đánh giá**, bất kể `ClusterPolicy` có khai `namespaces` gì. Vậy câu hỏi "mở rộng toàn cluster" thực chất chỉ có ý nghĩa với **`argocd`, `external-secrets`, `argo-rollouts`** — 3 namespace TF3 tự cài qua GitOps (`gitops/apps/*.yaml`), không phải add-on EKS quản lý.

Quét số liệu chi tiết theo từng yêu cầu (bảng đầy đủ, danh sách 58 image cluster-wide...) xem `docs/docx_cdo01/mandate-05-gap-analysis-20260718.md` mục 8.2-8.4. File này chỉ tóm tắt kết luận + phần ĐÃ LÀM.

---

## 2. Đã làm — `disallow-latest-tag` chuyển cluster-wide

**File:** `gitops/policies/kyverno/disallow-latest-tag.yaml`
**Sửa:** bỏ hẳn `namespaces: [techx-tf3]` khỏi `match.resources`, thêm comment giải thích không cần loại trừ `kube-system`/`kyverno` tường minh (đã bị webhook loại trừ).
**Lý do an toàn để làm ngay, không cần sửa gì trước:** quét toàn cluster — **0 vi phạm**. Cả 20 image first-party (ECR `techx-corp`, đều pin digest) lẫn 38 image "external" (EKS add-on, ArgoCD, Kyverno, Grafana, Postgres, karpenter...) đều dùng tag cố định hoặc digest, không cái nào `:latest`.
**Verify:**
```sh
kubectl apply --dry-run=server -f gitops/policies/kyverno/disallow-latest-tag.yaml
# clusterpolicy.kyverno.io/disallow-latest-tag configured (server dry run) -> hợp lệ
```

## 3. Đã làm — `custom-baseline-security-context` chuyển cluster-wide

**File:** `gitops/policies/kyverno/baseline-security-context.yaml`
**Sửa:** bỏ `namespaces: [techx-tf3]` khỏi **cả 8 rule** (dùng `replace_all` để sửa đồng loạt), thêm 1 comment chung ở đầu `spec:`. **Giữ nguyên 100%** toàn bộ `preconditions` (exception `kafka`/`aiops-engine`) — không đổi logic loại trừ, chỉ đổi phạm vi namespace.
**Lý do an toàn để làm ngay:** quét toàn cluster — `argocd`/`external-secrets`/`argo-rollouts` đều **0 vi phạm** (chart upstream của cả 3 đã hardening sẵn: `runAsNonRoot`, APE=false, drop-ALL, seccomp=RuntimeDefault). Chỉ `kube-system` có vi phạm thật (51/53 fail toàn cluster) nhưng đã bị webhook loại trừ sẵn, không cần lo.
**Verify:**
```sh
kubectl apply --dry-run=server -f gitops/policies/kyverno/baseline-security-context.yaml
# clusterpolicy.kyverno.io/custom-baseline-security-context configured (server dry run) -> hợp lệ
python3 -c "
import yaml
d = yaml.safe_load(open('gitops/policies/kyverno/baseline-security-context.yaml'))
for r in d['spec']['rules']:
    for m in r['match']['any']:
        assert 'namespaces' not in m['resources']
print('OK - khong con rule nao gioi han namespaces')
"
```

**Trạng thái 2 file này:** đã sửa xong trong working tree, **chưa commit/push/apply thật lên cluster** — đang chờ gộp chung 1 PR (xem mục 6).

---

## 4. `require-resource-requests` — CHƯA mở rộng, vì còn vi phạm thật ở `argocd`/`kyverno`/`argo-rollouts`

Khác 2 policy trên, đây là policy duy nhất có vi phạm thật nếu mở rộng ngay — nên **chưa đụng vào file `gitops/policies/kyverno/require-resource-requests.yaml`**, chỉ mới đi sửa từng workload cho sạch trước.

### 4.1. Kyverno — đã sửa. Request/limit cũ nằm ở đâu, tại sao chỉ cần thêm đúng `limits.cpu`?

**Trước khi sửa, `gitops/apps/kyverno-app.yaml` KHÔNG hề khai `resources:` cho bất kỳ controller nào** — chỉ có `replicas: 1` mỗi controller. Vậy `requests.cpu/memory` + `limits.memory` đang chạy sống **không nằm ở file nào trong repo cả** — verify trực tiếp bằng cách tải đúng chart + version mà `kyverno-app.yaml` đang trỏ tới:
```sh
helm repo add kyverno https://kyverno.github.io/kyverno/
helm show values kyverno/kyverno --version 3.3.4
```
→ Đây chính là nơi giá trị cũ tới từ đó — **default của chart upstream `kyverno/kyverno` bản 3.3.4**, không phải ai âm thầm khai tay:

| Controller | Field path trong chart | Default cũ (đã có sẵn) |
|---|---|---|
| `admissionController` | `admissionController.container.resources` (lồng qua `container:`, khác 3 cái dưới — xác nhận bằng `helm template` thử trước, không đoán) | `limits.memory: 384Mi`, `requests.cpu: 100m`, `requests.memory: 128Mi` |
| `backgroundController` | `backgroundController.resources` | `limits.memory: 128Mi`, `requests.cpu: 100m`, `requests.memory: 64Mi` |
| `cleanupController` | `cleanupController.resources` | như trên |
| `reportsController` | `reportsController.resources` | như trên |

Cả 4 đều **thiếu đúng 1 field: `limits.cpu`**. Vì Helm deep-merge object/map (khác với list bị thay thế toàn bộ — gotcha đã ghi ở chỗ khác trong repo, vd `sidecarContainers`), chỉ cần thêm đúng `limits.cpu` trong override, 3 field kia của chart default vẫn giữ nguyên, không cần copy lại cả block.

**Đã sửa** (`gitops/apps/kyverno-app.yaml`), verify bằng `helm template` với đúng nội dung file thật (không phải file test tạm) trước khi báo xong:
```yaml
admissionController:
  replicas: 1
  container:
    resources:
      limits:
        cpu: 300m
backgroundController:
  replicas: 1
  resources:
    limits:
      cpu: 200m
reportsController:
  replicas: 1
  resources:
    limits:
      cpu: 200m
cleanupController:
  replicas: 1
  resources:
    limits:
      cpu: 200m
```
Kết quả render (`helm template kyverno kyverno/kyverno --version 3.3.4 -f <values-thật-trong-file> -n kyverno`):
```
kyverno-admission-controller / kyverno  -> limits: {cpu: 300m, memory: 384Mi}  requests: {cpu: 100m, memory: 128Mi}
kyverno-background-controller / controller -> limits: {cpu: 200m, memory: 128Mi}  requests: {cpu: 100m, memory: 64Mi}
kyverno-cleanup-controller / controller -> limits: {cpu: 200m, memory: 128Mi}  requests: {cpu: 100m, memory: 64Mi}
kyverno-reports-controller / controller -> limits: {cpu: 200m, memory: 128Mi}  requests: {cpu: 100m, memory: 64Mi}
```
Đủ 4 field cho cả 4 controller, memory không bị mất. **300m/200m là giá trị đề xuất theo tỷ lệ ~2-3x request (300m cho admission-controller vì đây là controller quan trọng nhất, chặn toàn bộ admission nếu chậm) — có thể điều chỉnh nếu team muốn số khác, không có ràng buộc kỹ thuật bắt buộc đúng số này.**

### 4.2. `argo-rollouts` — đã sửa, đơn giản hơn

**File:** `gitops/apps/argo-rollouts-app.yaml` — khác Kyverno, file này **đã có sẵn** `controller.resources.requests.{cpu,memory}` + `limits.memory`, chỉ thiếu đúng `limits.cpu`. Đã thêm:
```yaml
controller:
  resources:
    requests:
      cpu: 100m
      memory: 128Mi
    limits:
      cpu: 300m        # <- dòng mới thêm
      memory: 256Mi
```
Verify bằng `helm template argo-rollouts argo/argo-rollouts --version 2.41.0 -f <values-thật> -n argo-rollouts`:
```
argo-rollouts / argo-rollouts -> limits: {cpu: 300m, memory: 256Mi}  requests: {cpu: 100m, memory: 128Mi}
```

### 4.3. `argocd` — CHƯA sửa được, vì không có file nào trong repo để sửa

Verify: `helm list -n argocd` → rỗng (không phải Helm release). `kubectl describe deploy argocd-server` → có `kubectl.kubernetes.io/last-applied-configuration` (dấu hiệu `kubectl apply` tay/CI-ngoài-repo thẳng manifest gốc, không qua GitOps của repo này). Không tìm thấy script bootstrap ArgoCD nào trong `deploy/`/`scripts/`/`.github/workflows/`. Version đang chạy: `quay.io/argoproj/argocd:v3.4.5`.

**3 hướng xử lý thật, đánh đổi khác nhau — CẦN QUYẾT ĐỊNH trước khi mở rộng `require-resource-requests` sang `argocd`:**

| Hướng | Cách làm | Rủi ro | Đúng tinh thần GitOps? |
|---|---|---|---|
| **A. Patch nhanh, tạm thời** | `kubectl patch` trực tiếp từng Deployment/StatefulSet ArgoCD, thêm `resources:` | Thấp, làm ngay được — nhưng đây là thay đổi **ngoài Git**, không ai theo dõi, dễ mất nếu sau này có ai `kubectl apply` lại manifest gốc (drift, không phát hiện được) | ❌ Không — chỉ vá tạm |
| **B. Vendor Kustomize overlay** | Tải đúng `install.yaml` (bản v3.4.5, non-HA hoặc `ha/install.yaml` tuỳ đang chạy bản nào) vào repo (vd `gitops/bootstrap/argocd/`), viết `kustomization.yaml` + strategic-merge patch thêm `resources:` từng container, apply bằng `kubectl apply -k` | Trung bình — vẫn phải chạy tay 1 lần đầu (ArgoCD không tự quản lý chính nó từ số 0), nhưng từ sau sửa gì cũng qua Git | 🟡 Một phần — bootstrap đầu vẫn imperative, phần sau đúng GitOps |
| **C. Chuyển hẳn sang Helm chart chính thức `argo/argo-cd`, để ArgoCD tự quản lý chính nó** | `helm upgrade --install` 1 lần đầu (ngoài GitOps, bắt buộc vì "con gà quả trứng"), sau đó tạo 1 `Application` trỏ vào chính chart này (pattern "app of apps" chuẩn ArgoCD) | Cao nhất — đổi từ raw manifest sang Helm chart có thể lệch behavior/CRD so với bản đang chạy, cần test kỹ ở môi trường không phải production trước; lỡ tay lúc cutover có thể mất luôn quyền điều khiển GitOps của cả cluster | ✅ Đầy đủ nhất, đúng chuẩn dài hạn |

**Khuyến nghị:** hướng B — cân bằng giữa rủi ro và đúng chuẩn GitOps, tách thành 1 task riêng (không làm vội trong lúc dọn Mandate 5). Hướng C nên để dành cho 1 mandate/task khác, có kế hoạch rollback rõ ràng.

### 4.3.1. Phân tích downtime từng hướng — đưa cho cả 2 team quyết định

**Điều quan trọng nhất cần biết trước:** cả 3 hướng đều **chỉ động vào chính component của ArgoCD**, **không đụng bất kỳ workload nào của `techx-tf3`** (`payment`, `checkout`, `cart`...). ArgoCD chỉ là công cụ triển khai/đồng bộ, không phải thứ đang phục vụ traffic khách hàng thật.

→ **Storefront/traffic khách hàng: 0 ảnh hưởng ở cả 3 hướng.** "Downtime" ở đây nghĩa là: trong lúc đó ArgoCD tạm thời không sync/self-heal được, UI/CLI ArgoCD tạm lỗi — nếu đúng lúc đó có 1 pod TF3 nào crash thật, self-heal sẽ **chờ tới khi ArgoCD sống lại** mới tự sửa (thay vì tức thời), chứ không phải khách hàng thấy lỗi.

**Cấu hình hiện tại — mọi component ArgoCD đều chỉ chạy 1 replica (không HA):**

| Component | Kind | Replicas | Update strategy |
|---|---|---|---|
| `argocd-server` | Deployment | 1 | RollingUpdate |
| `argocd-repo-server` | Deployment | 1 | RollingUpdate |
| `argocd-applicationset-controller` | Deployment | 1 | RollingUpdate |
| `argocd-redis` | Deployment | 1 | RollingUpdate |
| `argocd-dex-server` | Deployment | 1 | RollingUpdate |
| `argocd-notifications-controller` | Deployment | 1 | **Recreate** (khác 5 cái trên) |
| `argocd-application-controller` | StatefulSet | 1 | RollingUpdate (kiểu StatefulSet — khác kiểu Deployment) |

Vì tất cả chỉ 1 replica, bất kỳ thay đổi nào khiến pod template đổi (kể cả chỉ thêm `resources:`) đều kích hoạt restart — câu hỏi là restart kiểu nào, có tạo pod mới trước khi giết pod cũ hay không:

- **6 Deployment dùng `RollingUpdate`**: mặc định `maxSurge=25%→làm tròn lên 1`, `maxUnavailable=25%→làm tròn xuống 0` khi replicas=1 → Kubernetes **tạo pod MỚI trước, đợi Ready, rồi mới giết pod CŨ** → downtime gần như 0 (vài giây gián đoạn API call đang xử lý dở).
- **`argocd-notifications-controller` dùng `Recreate`**: giết pod cũ HẲN rồi mới tạo pod mới → có khoảng trống thật, thường vài giây tới ~30s. Component gửi thông báo, không nằm trong đường sync chính — ảnh hưởng thấp nhất.
- **`argocd-application-controller` là StatefulSet**: cơ chế `RollingUpdate` của StatefulSet khác Deployment — giết pod cũ trước, đợi terminate xong, rồi mới tạo pod mới (không surge trước) → có khoảng trống thật, thường 10-30s. Đây là bộ não chính (reconciliation loop) — trong khoảng trống này **không app nào được sync/self-heal**, nhưng app đã deploy vẫn chạy bình thường.

**Downtime hướng A (`kubectl patch`) và hướng B (Kustomize + `kubectl apply -k`) — giống hệt nhau tại thời điểm apply**, vì cùng động vào đúng 7 Deployment/StatefulSet trên, cùng update strategy, cùng cơ chế Kubernetes xử lý restart. Khác biệt giữa A và B không nằm ở downtime, mà ở quy trình quản lý (B theo dõi qua Git, A thì không). Làm từng component một (khuyến nghị, không dồn 1 lần): tổng cửa sổ "ArgoCD chưa hoàn chỉnh" khoảng 2-5 phút rải rác, riêng phần **mất khả năng tự sync/self-heal thật sự** chỉ nằm ở lúc restart `argocd-application-controller` (~10-30s). Rủi ro phụ riêng của hướng B: nếu bản `install.yaml` vendor vào repo không khớp 100% với cấu hình đang chạy sống (vd có ai từng chỉnh tay 1 chỗ ngoài Git), `kubectl apply -k` có thể vô tình reset lại chỗ đó — nên `kubectl diff -k` trước, không apply mù.

**Downtime hướng C (chuyển sang Helm chart `argo/argo-cd`) — cao hơn hẳn, khác bản chất:**
- Resource hiện tại tạo bằng `kubectl apply` thô, không có annotation sở hữu của Helm — `helm install`/`upgrade` sẽ **từ chối** ghi đè (lỗi "invalid ownership metadata") trừ khi dùng `--take-ownership` hoặc phải **xoá sạch rồi cài lại từ đầu**.
- Nếu phải xoá-cài-lại: downtime thật, có thể **vài phút tới 10+ phút** — ArgoCD hoàn toàn không tồn tại trong lúc đó, không sync/self-heal được gì (vẫn không ảnh hưởng storefront trực tiếp, nhưng mất self-heal lâu hơn nếu có sự cố đúng lúc đó).
- **Rủi ro ngoài downtime, còn nặng hơn:** `argocd-secret` đang giữ password admin, TLS cert, credential đọc repo GitHub (`Phase3-TF3-Infra-Sentinel`), cấu hình SSO/Dex. Nếu xoá-cài-lại mà không backup/export đúng cách trước, **mất hết các credential này** — phải cấu hình lại tay từ đầu, việc lớn hơn hẳn phạm vi "thêm resources.limits.cpu". Nên tách hẳn thành 1 task/mandate riêng, có kế hoạch backup + rollback rõ ràng, có schedule maintenance window báo trước cho cả 2 team.

**Bảng so sánh nhanh:**

| | Hướng A (patch tay) | Hướng B (Kustomize) | Hướng C (Helm migrate) |
|---|---|---|---|
| Downtime ArgoCD (ước tính) | ~10-30s thật sự mất self-heal, rải rác 2-5 phút tổng | Tương đương A | Vài phút → vài chục phút (nếu phải xoá-cài-lại) |
| Ảnh hưởng storefront/khách hàng | Không | Không | Không (nhưng mất self-heal lâu hơn nếu có sự cố đúng lúc đó) |
| Rủi ro mất cấu hình (secret/SSO/repo creds) | Không | Không | **Có, nếu không backup kỹ trước** |
| Theo dõi qua Git từ giờ về sau | Không | Có | Có |
| Nên làm trong lúc dọn Mandate 5 hay tách riêng | Có thể làm ngay | Có thể làm, nên làm | Nên tách task riêng, có kế hoạch backup/rollback + maintenance window |

**Chưa quyết định — cần bạn và CDO02 cùng chọn hướng trước khi làm tiếp phần ArgoCD.**

**Nếu chọn hướng B:** quy trình đầy đủ, từng lệnh, kèm số liệu request/limit đề xuất cho cả 7 container — đã viết thành runbook riêng: [`docs/runbooks/argocd-resource-limits-kustomize-adoption.md`](../runbooks/argocd-resource-limits-kustomize-adoption.md).

---

## 5. Tổng kết trạng thái ngay lúc này (19/07, cập nhật sau khi apply thật)

| Việc | Trạng thái |
|---|---|
| `disallow-latest-tag` → cluster-wide | ✅ Đã sửa file, chưa commit |
| `custom-baseline-security-context` → cluster-wide | ✅ Đã sửa file, chưa commit |
| `require-resource-requests` → cluster-wide | ✅ Đã sửa file, chưa commit (bỏ `namespaces: [techx-tf3]`, dry-run apply hợp lệ) |
| `kyverno` — thêm `limits.cpu` | ✅ Đã sửa file (theo đề xuất `kyverno-kube-system-resources-proposal.md`: admission-controller lên `1000m`, xem lý do trong comment file), chưa commit — chờ merge+sync mới lên cluster thật |
| `argo-rollouts` — thêm `limits.cpu` | ✅ Đã sửa file, chưa commit — chờ merge+sync |
| `argocd` — chọn **hướng B (Kustomize)**, đã apply thật lên cluster | ✅ **XONG, verify sống 19/07** — xem chi tiết mục 5.1 |
| `require-first-party-image-digest` → cluster-wide | Không cần đổi gì — regex tự giới hạn đúng phạm vi ECR `techx-corp` |

### 5.1. Chi tiết đã apply thật cho ArgoCD (hướng B)

- Vendor `gitops/bootstrap/argocd/base/install.yaml` (v3.4.5) — verify trước `kubectl diff -n argocd -f base/install.yaml` = **0 khác biệt** với cluster sống (an toàn, không có chỉnh tay ngoài Git nào bị patch đè).
- `gitops/bootstrap/argocd/kustomization.yaml` — patch thêm `resources` cho **10 container/initContainer** (7 container chính + 3 initContainer `copyutil`×2/`secret-init` phát hiện bổ sung khi quét lại sau lần apply đầu — script quét đầu chỉ check `spec.containers`, bỏ sót `spec.initContainers`).
- Apply thật theo 2 đợt như kế hoạch: đợt 1 (5 Deployment RollingUpdate) → rollout thành công tức thì; đợt 2 (`argocd-application-controller` StatefulSet + `argocd-notifications-controller` Recreate) → rollout xong trong ~67 giây (11:52:56 → 11:54:03 UTC), khớp đúng dự đoán downtime ở mục 4.3.1. Sau đó phát hiện+vá bổ sung 3 initContainer, apply lại 3 Deployment liên quan (rollout thành công).
- **Verify cuối:** `10/10 container/initContainer` trong `argocd` đủ 4 field, không pod nào ngoài `Running`, toàn bộ 11 `Application` vẫn `Synced/Healthy` (trừ `flagd-secret-sync` `OutOfSync` — xác nhận có từ trước, không liên quan), storefront `200 OK` xuyên suốt.
- **Đã viết `gitops/apps/argocd-self-app.yaml`** (hướng B2) — `Application` tự trỏ vào `gitops/bootstrap/argocd`, được `techx-corp-bootstrap` (app-of-apps quét `gitops/apps/`) tự phát hiện sau khi merge, từ đó về sau sửa gì trong thư mục này cũng tự động sync, không cần `kubectl apply -k` tay nữa. Đã ghi rõ trong comment: **bắt buộc `kubectl diff -k` trước khi merge bất kỳ PR nào đụng thư mục này** — rủi ro tự-deadlock nếu 1 lần sửa sau làm hỏng chính ArgoCD.

**Lưu ý còn treo:** `kyverno`/`argo-rollouts` mới sửa trong Git, **chưa merge nên chưa lên cluster thật** — nếu merge `require-resource-requests` cluster-wide trước khi 2 PR đó lên, `argo-rollouts` (không bị webhook loại trừ) sẽ tạm có 1 vi phạm thật trong PolicyReport cho tới khi merge xong (không chặn gì vì pod đã tồn tại sẵn, `allowExistingViolations` mặc định `true` chỉ ảnh hưởng update sau này) — nên merge cả 2 PR gần nhau, không để cách quá xa.

## 6. Việc cần làm tiếp

1. Gộp các file đã sửa (`disallow-latest-tag.yaml`, `baseline-security-context.yaml`, `require-resource-requests.yaml`, `kyverno-app.yaml`, `argo-rollouts-app.yaml`, `gitops/bootstrap/argocd/**`, `gitops/apps/argocd-self-app.yaml`) vào 1 hoặc vài PR.
2. Merge — theo dõi `techx-corp-bootstrap` tự phát hiện `argocd-self` Application, và `argocd`/`argo-rollouts` Application tự sync đúng resources đã khai.
3. Verify lại toàn cluster bằng đúng script quét đã dùng ở mục 8 của `docs/docx_cdo01/mandate-05-gap-analysis-20260718.md`, xác nhận 0 vi phạm thật ở `argocd`/`kyverno`/`argo-rollouts`/`external-secrets`.
