# Fix `require-run-as-non-root` — thiếu fallback cấp Pod, gây FAIL nhầm (không phải lỗ hổng bảo mật thật)

**Ngày:** 19-20/07/2026
**File sửa:** `gitops/policies/kyverno/baseline-security-context.yaml`, rule `require-run-as-non-root`

---

## 1. Vì sao phát hiện ra — bối cảnh

Sau khi mở rộng `custom-baseline-security-context` sang cluster-wide (PR #258) và vá xong resource request/limit cho `argocd`/`kyverno`/`argo-rollouts`, verify lại `kubectl get policyreport -A` vẫn còn 2 nhóm FAIL thật:
- `argo-rollouts` (cả 2 replica) — rule `require-run-as-non-root`
- `argocd-notifications-controller`, `argocd-redis` — rule `require-run-as-non-root`

Test trực tiếp (không phải dry-run, apply lại y hệt manifest đang chạy sống — mô phỏng đúng 1 lần ArgoCD tự sync bình thường):

```sh
kubectl -n argo-rollouts get deploy argo-rollouts -o yaml > /tmp/argo-rollouts-live.yaml
kubectl apply --dry-run=server -f /tmp/argo-rollouts-live.yaml
```
```
Error from server: ... admission webhook "validate.kyverno.svc-fail" denied the request:
custom-baseline-security-context:
  require-run-as-non-root: 'validation failure: Containers must set runAsNonRoot: true.'
```

→ Đây **không phải chỉ là báo cáo sai** — vì policy đang `Enforce`, nó **thật sự chặn** mọi lần ArgoCD tự sync các Deployment này. Đây chính là rủi ro tự-deadlock: nếu `argocd-self`/`argo-rollouts` Application cần cập nhật resource này (kể cả chỉ đồng bộ lại bình thường), sẽ bị chặn.

## 2. Nguyên nhân gốc — đã xác minh trực tiếp

Kiểm tra `securityContext` thật của 3 pod đang bị chặn:

```sh
kubectl -n argo-rollouts get pod <pod> -o jsonpath='pod={.spec.securityContext.runAsNonRoot} container={.spec.containers[0].securityContext.runAsNonRoot}'
```

| Pod | `securityContext.runAsNonRoot` cấp Pod | cấp container |
|---|---|---|
| `argo-rollouts-*` | `true` | *(không khai)* |
| `argocd-notifications-controller-*` | `true` | *(không khai)* |
| `argocd-redis-*` | `true` | *(không khai)* |

Cả 3 chỉ khai `runAsNonRoot: true` ở **cấp Pod** — theo đúng chuẩn Kubernetes, giá trị này **kế thừa xuống mọi container bên trong** trừ khi container tự ghi đè. Đây là cách khai **hợp lệ và đủ an toàn** (không phải lỗ hổng) — bằng chứng: rule song song `require-effective-non-root` (cùng file, cùng mục đích kiểm tra non-root) đã **PASS** cho cả 3 pod này, vì rule đó có đọc đúng cấp Pod.

So sánh 2 rule cùng policy:

```yaml
# require-run-as-non-root (LOI) — chi doc container, khong fallback
- key: "{{ element.securityContext.runAsNonRoot || `false` }}"

# require-effective-non-root (DUNG, rule khac cung file) — co du fallback len Pod
- key: "{{ element.securityContext.runAsNonRoot || request.object.spec.jobTemplate.spec.template.spec.securityContext.runAsNonRoot || request.object.spec.template.spec.securityContext.runAsNonRoot || request.object.spec.securityContext.runAsNonRoot || `false` }}"
```

`require-run-as-non-root` chỉ đọc `element.securityContext.runAsNonRoot` (container hiện tại trong `foreach`), **không có nhánh nào đọc lên `request.object.spec...securityContext.runAsNonRoot`** (cấp Pod/PodTemplate) khi container không tự khai. Container không khai → `element.securityContext.runAsNonRoot` rỗng → `|| \`false\`` → so `NotEquals true` → **FAIL nhầm**.

**Lưu ý quan trọng:** dòng `list:` (chọn đúng mảng container theo kind) và `match.kinds` (Pod/Deployment/StatefulSet/...) đều **đúng, không phải nguyên nhân** — cả 2 đã đúng nhận diện đúng resource/container cần xét. Lỗi nằm đúng 1 chỗ: biểu thức `key:` trong `deny.conditions`, phần đọc giá trị `runAsNonRoot` của TỪNG container, thiếu vế fallback.

## 3. Cách sửa

Thêm đúng 3 vế fallback (theo thứ tự CronJob → Deployment/StatefulSet/... → Pod trần) vào biểu thức, y hệt pattern đã dùng ở `require-effective-non-root`:

```yaml
- key: "{{ element.securityContext.runAsNonRoot || request.object.spec.jobTemplate.spec.template.spec.securityContext.runAsNonRoot || request.object.spec.template.spec.securityContext.runAsNonRoot || request.object.spec.securityContext.runAsNonRoot || `false` }}"
  operator: NotEquals
  value: true
```

## 4. Verify sau khi sửa — bằng chứng thật

```sh
kubectl apply --dry-run=server -f gitops/policies/kyverno/baseline-security-context.yaml
# clusterpolicy.kyverno.io/custom-baseline-security-context configured (server dry run) -> hop le cu phap

# Test lai dung 3 case tung bi chan
kubectl apply --dry-run=server -f /tmp/argo-rollouts-live.yaml    # -> configured (server dry run)
kubectl apply --dry-run=server -f /tmp/argocd-redis-live.yaml     # -> configured (server dry run)
kubectl apply --dry-run=server -f /tmp/argocd-notif-live.yaml     # -> configured (server dry run)

# Xac nhan khong lam hong exception dang co (kafka)
kubectl -n techx-tf3 get deploy kafka -o yaml > /tmp/kafka-live.yaml
kubectl apply --dry-run=server -f /tmp/kafka-live.yaml            # -> configured (server dry run)

# Suc khoe tong the sau khi apply that len cluster
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded
kubectl -n techx-tf3 exec deploy/grafana -c grafana -- wget -qO- --server-response "http://frontend-proxy:8080/"
```

**Kết quả (19-20/07):** cả 3 case từng bị chặn đều qua (`configured`, không còn lỗi admission webhook). `kafka` (có exception riêng cho `require-run-as-non-root` không cần vì bản thân container `kafka` chính đã `runAsNonRoot: true` cấp container, chỉ `init-kafka-data` mới cần root — không bị ảnh hưởng bởi rule này) vẫn qua bình thường. Không pod nào ngoài `Running`/`Succeeded` trong toàn cluster, storefront `200 OK`.

## 5. Vì sao đây từng gây sự cố thật (bài học)

Rule này (và các rule `deny.conditions` viết theo lối cũ khác trong cùng file, đã fix một phần ở PR #229/#232) minh hoạ đúng 1 lớp bug dễ tái diễn: khi Kyverno autogen hoặc mở rộng `match.kinds` sang nhiều loại controller, **mọi biểu thức đọc field cấp container BẮT BUỘC phải có fallback lên field tương ứng cấp Pod/PodTemplate** — nếu không, rule sẽ FAIL NHẦM với bất kỳ workload nào chọn cách khai ở cấp Pod (một cách khai hoàn toàn hợp lệ, không hiếm gặp — nhiều chart Helm upstream, kể cả `argo-rollouts`/`argocd` chính thức, dùng đúng kiểu này). Khi policy ở `Enforce`, FAIL nhầm này **không chỉ là báo cáo sai** — nó **thật sự chặn admission**, có thể gây sự cố vận hành thật (đã xảy ra với `argo-rollouts`/`argocd-self` trong phiên làm việc này).

**Khuyến nghị cho các rule tương lai trong policy này:** trước khi thêm rule mới hoặc mở rộng `match.kinds`, luôn kiểm tra: biểu thức đọc `securityContext.*` có đủ 4 nhánh fallback (CronJob/controller/Pod trần) như `require-effective-non-root` đã làm mẫu hay chưa — dùng đúng bảng test ở mục 4 để tự verify trước khi Enforce.
