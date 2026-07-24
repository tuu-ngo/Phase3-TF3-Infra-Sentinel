# Mandate #5 Remediation — Gap Analysis: dịch Kyverno → CEL/ValidatingAdmissionPolicy (VAP)

**Jira:** [PM-167](https://laynitroepic.atlassian.net/browse/PM-167) — "Audit khả năng CEL/VAP cho 4 rule Kyverno + chuyển Kyverno Enforce→Audit tạm thời (stopgap khẩn)"<br>
**Epic:** [PM-166](https://laynitroepic.atlassian.net/browse/PM-166) — "[MANDATE 5 REMEDIATION] Chuyển admission enforcement từ Kyverno sang native ValidatingAdmissionPolicy (VAP) — mentor fail do dùng công cụ non-native"<br>
**Ngày viết:** 21/07/2026<br>
**Người viết:** CDO01<br>
**Trạng thái:** Phần 1 (mapping CEL) — hoàn tất phân tích tĩnh. Phần 2 (xác nhận schema CRD `Rollout`) — **CHƯA xác nhận, cần cluster access** (xem mục 4). Phần 3-4 (cutover Enforce→Audit) — **chưa thực hiện**, đây là task riêng theo dõi ở PM-167 mục 3-4, không nằm trong phạm vi doc phân tích này.

---

## 0. Vì sao có task này

Mentor đánh **FAIL** Mandate #5 vì phần admission enforcement dùng Kyverno — một **công cụ third-party** (dù open-source, có governance riêng, không phải built-in Kubernetes) — trong khi từ Kubernetes 1.30, `ValidatingAdmissionPolicy` (VAP) đã **GA**, cho phép viết cùng loại policy bằng CEL (Common Expression Language) **native trong API server**, không cần cài thêm webhook/controller/CRD nào. Cluster hiện tại (`techx-corp-tf3`) chạy **EKS 1.35** — thừa điều kiện để dùng VAP GA.

Việc "sài công cụ ngoài" tự nó **không sai kỹ thuật** (Kyverno vẫn là lựa chọn hợp lý, được CNCF graduated), nhưng mentor yêu cầu rõ **native trước, third-party sau** cho baseline admission control. Quyết định remediation (đã chốt ở Epic PM-166, không phải quyết định của doc này):

1. **Xây VAP làm lớp enforcement chính** cho 4 nhóm rule baseline (non-root, no-latest-tag, first-party-digest, resource-requests).
2. **Giữ lại Kyverno**, nhưng hạ từ `Enforce` xuống `Audit` — không gỡ bỏ hoàn toàn, vì Kyverno vẫn làm được vài việc VAP chưa làm được (xem mục 5): `verifyImages`/Cosign, PolicyReport dashboard, `foreach`+JMESPath phức tạp hơn CEL ở vài chỗ.
3. Khoảng thời gian giữa lúc Kyverno hạ Audit và VAP lên Enforce là **cửa sổ rủi ro thật** — không có gì chặn thật tại admission trong lúc đó (xem mục 6).

Doc này là **bước 1** (yêu cầu 1+2 của PM-167): dịch từng rule sang CEL trước khi viết `ValidatingAdmissionPolicy` YAML thật, để biết chắc cái gì dịch được 1:1, cái gì cần thiết kế lại, cái gì VAP không làm được — tránh vừa viết VAP vừa mới phát hiện gap giữa chừng.

---

## 1. Nền tảng kỹ thuật: VAP khác Kyverno ở đâu (ảnh hưởng trực tiếp tới cách dịch)

| | Kyverno `ClusterPolicy` | `ValidatingAdmissionPolicy` (VAP) |
|---|---|---|
| Ngôn ngữ điều kiện | JMESPath (`preconditions`, `deny.conditions`) + pattern-matching | CEL (Common Expression Language) |
| Nơi chạy | Webhook riêng do Kyverno controller expose (`validate.kyverno.svc-fail`) | Ngay trong `kube-apiserver`, không có webhook/pod riêng |
| Match nhiều `kind` trong 1 policy | 1 `match.resources.kinds` list tự do (Pod, Deployment, StatefulSet, Rollout, ...) | Mỗi `matchConstraints.resourceRules[]` phải khai đúng `(apiGroups, apiVersions, resources)` — **không có 1 rule "match nhiều group khác nhau cùng lúc"**, phải liệt kê nhiều `resourceRules` entry |
| Autogen (Pod rule → tự nhân cho Deployment/StatefulSet/...) | Có (nhưng từng có gap thật với `Rollout`, đã fix tay ở PR #232 — xem mục 9 báo cáo Mandate #5) | **Không có autogen.** Phải tự khai từng `resourceRule` + tự viết CEL branch theo `object.kind`, giống hệt cách PR #232 đã làm tay cho Kyverno — không phải việc mới, chỉ là làm lại bằng CEL |
| Loại trừ theo điều kiện (kafka/aiops-engine) | `preconditions` per-rule (JMESPath, linh hoạt per-rule) | `matchConditions` (CEL, áp cho **toàn bộ policy**, không phải per-rule) — nếu 1 policy có nhiều rule với precondition khác nhau (baseline-security-context đang vậy), phải **nhúng điều kiện loại trừ vào trong từng `validations[].expression`** thay vì dùng `matchConditions`, hoặc tách thành nhiều VAP nhỏ hơn. Doc này chọn nhúng vào expression để giữ 1 VAP tương ứng 1 ClusterPolicy — xem mục 3.
| Namespace scope | `match.resources.namespaces: [tên cụ thể]` — so khớp theo **tên** | `matchConstraints.namespaceSelector` — so khớp theo **label** của namespace, KHÔNG so theo tên trực tiếp. **Gap thật phát hiện khi audit** — xem mục 3.3. |
| Biến dùng lại giữa nhiều rule | Không có khái niệm biến chung, JMESPath lặp lại từng chỗ (đúng như 4 file hiện tại đang lặp `request.object.spec.template.spec.containers || ...` nhiều lần) | `spec.variables[]` — tính 1 lần, tái dùng ở mọi `validations[]` trong cùng policy. **Tốt hơn Kyverno ở điểm này** — gọn hơn nhiều so với JMESPath fallback-chain lặp lại. |
| Audit / Enforce | `validationFailureAction: Audit \| Enforce` trên `ClusterPolicy` | `ValidatingAdmissionPolicyBinding.spec.validationActions: [Deny] \| [Warn] \| [Audit]` — tách biệt: **policy** (`ValidatingAdmissionPolicy`) định nghĩa luật, **binding** (`ValidatingAdmissionPolicyBinding`) định nghĩa scope + hành động khi fail. Có thể dùng nhiều `validationActions` cùng lúc (vd `[Audit, Warn]` khi đang rà). |
| Background scan / PolicyReport | Có (`background: true` → Kyverno tự quét resource đã tồn tại, sinh `PolicyReport`) | **Không có.** VAP chỉ chạy tại admission-time cho request mới — không tự quét lại resource cũ đang chạy. Đây là **gap thật**, ảnh hưởng trực tiếp mục "reconcile PolicyReport" đang treo ở báo cáo Mandate #5 (mục 9). |
| Ký ảnh/Cosign (`verifyImages`) | Có, native trong Kyverno | **Không có tương đương CEL native** — CEL không tự gọi ra ngoài để verify chữ ký. Đây là lý do chính giữ lại Kyverno song song thay vì gỡ hẳn (PM-114 vẫn cần Kyverno). |

**Kết luận nền tảng:** VAP dịch được phần lớn 4 policy hiện tại (chúng đều là pattern-matching/regex thuần trên field có sẵn — đúng thế mạnh của CEL), nhưng **không phải drop-in 1:1** — cần thiết kế lại cách xử lý exception (matchConditions vs nhúng expression), namespace scoping (label vs tên), và **không thay được** 2 việc: background reconciliation + Cosign verify. Đây chính là lý do Kyverno **giữ lại ở Audit**, không gỡ hẳn.

---

## 2. Bảng ánh xạ CEL — theo từng `ClusterPolicy`

Ký hiệu độ tin cậy dịch:
- 🟢 **Dịch 1:1, tin cậy cao** — logic thuần regex/field-check, không phụ thuộc gap chưa xác nhận.
- 🟡 **Dịch được, nhưng cần thiết kế lại cách áp dụng** (không 1:1 cú pháp) — namespace scoping, exception, hoặc gộp rule.
- 🔴 **Không dịch được bằng CEL thuần** — cần cơ chế khác hoặc giữ ở Kyverno.

Toàn bộ CEL dưới đây là **bản dịch nháp để đánh giá khả thi**, chưa chạy thử trên cluster thật — trước khi enforce thật phải test bằng `kubectl apply --dry-run=server` với đúng bộ fixture vi phạm đang có ở `docs/evidence/mandate-05/rejection-demo/*.yaml` (như đã làm với Kyverno), không tin theo bản nháp này.

### 2.1 `disallow-latest-tag` — 🟢 dịch 1:1, tin cậy cao nhất trong 4 policy

Nguồn: `gitops/policies/kyverno/disallow-latest-tag.yaml`, chỉ match `kind: Pod`, 1 rule duy nhất, không có exception/precondition.

| Kyverno (JMESPath `regex_match`) | CEL tương đương |
|---|---|
| `regex_match('^(.+/)?[^/@]+:latest$', element.image)` phải **false**, và `regex_match('^.+(:[^/]+\|@sha256:[0-9a-f]{64})$', element.image)` phải **true** — áp cho `containers`, `initContainers`, `ephemeralContainers` | Xem khối CEL dưới |

```yaml
# ValidatingAdmissionPolicy nháp — disallow-latest-tag
spec:
  matchConstraints:
    resourceRules:
      - apiGroups: [""]
        apiVersions: ["v1"]
        resources: ["pods"]
        operations: ["CREATE", "UPDATE"]
  validations:
    - expression: >
        object.spec.containers.all(c,
          !c.image.matches('^(.+/)?[^/@]+:latest$') &&
          c.image.matches('^.+(:[^/]+|@sha256:[0-9a-f]{64})$')) &&
        (!has(object.spec.initContainers) || object.spec.initContainers.all(c,
          !c.image.matches('^(.+/)?[^/@]+:latest$') &&
          c.image.matches('^.+(:[^/]+|@sha256:[0-9a-f]{64})$'))) &&
        (!has(object.spec.ephemeralContainers) || object.spec.ephemeralContainers.all(c,
          !c.image.matches('^(.+/)?[^/@]+:latest$') &&
          c.image.matches('^.+(:[^/]+|@sha256:[0-9a-f]{64})$')))
      message: "Images must use an explicit non-latest tag or immutable digest."
```

**Ghi chú:** CEL `string.matches()` dùng RE2 (Go `regexp`), cùng engine với Kyverno `regex_match` — 2 pattern regex copy nguyên xi, không cần viết lại cú pháp. Không có exception nào trong policy gốc nên không cần `matchConditions`. Vì chỉ match `kind: Pod`, không cần biến `variables` để xử lý nhiều kind.

### 2.2 `require-first-party-image-digest` — 🟡 dịch được, nhưng namespace scoping phải thiết kế lại

Nguồn: chỉ match `kind: Pod`, **namespace `techx-tf3`**, 1 rule.

**Gap thật phát hiện khi audit (mục 1, bảng trên):** Kyverno `match.resources.namespaces: [techx-tf3]` so theo **tên namespace** trực tiếp. VAP `matchConstraints.namespaceSelector` chỉ so theo **label** — không có field nào so theo tên namespace thẳng. Hai hướng xử lý:

1. **Gắn label cho namespace** `techx-tf3` (vd `techx.io/mandate5-scope: first-party-digest`) rồi dùng `namespaceSelector.matchLabels`. Cần 1 thay đổi hạ tầng nhỏ (label namespace qua GitOps), không phải chỉ đổi policy.
2. **Nhúng check namespace vào trong `validations[].expression`** bằng `namespaceObject.metadata.name` — VAP hỗ trợ biến `namespaceObject` sẵn có trong CEL context, không cần thêm label. **Khuyến nghị dùng cách này** — không đụng hạ tầng namespace, giữ đúng 1:1 hành vi hiện tại (so theo tên).

```yaml
spec:
  matchConstraints:
    resourceRules:
      - apiGroups: [""]
        apiVersions: ["v1"]
        resources: ["pods"]
        operations: ["CREATE", "UPDATE"]
  matchConditions:
    - name: scope-to-techx-tf3
      expression: "namespaceObject.metadata.name == 'techx-tf3'"
  validations:
    - expression: >
        object.spec.containers.all(c,
          !c.image.startsWith('197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp') ||
          c.image.matches('^197826770971\\.dkr\\.ecr\\.ap-southeast-1\\.amazonaws\\.com/techx-corp@sha256:[0-9a-f]{64}$')) &&
        (!has(object.spec.initContainers) || object.spec.initContainers.all(c,
          !c.image.startsWith('197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp') ||
          c.image.matches('^197826770971\\.dkr\\.ecr\\.ap-southeast-1\\.amazonaws\\.com/techx-corp@sha256:[0-9a-f]{64}$'))) &&
        (!has(object.spec.ephemeralContainers) || object.spec.ephemeralContainers.all(c,
          !c.image.startsWith('197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp') ||
          c.image.matches('^197826770971\\.dkr\\.ecr\\.ap-southeast-1\\.amazonaws\\.com/techx-corp@sha256:[0-9a-f]{64}$')))
      message: "Images from 197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp must use @sha256:<64 lowercase hex>."
```

**Ghi chú:** logic "nếu là image first-party ECR thì bắt buộc digest, nếu không phải thì bỏ qua" dịch 1:1 bằng `startsWith` + `matches`. Đánh dấu 🟡 (không phải 🔴) vì gap chỉ nằm ở namespace-scoping, đã có hướng xử lý rõ (`namespaceObject`), không phải chặn cứng.

### 2.3 `require-resource-requests` — 🟢 dịch 1:1, không có exception

Nguồn: chỉ match `kind: Pod`, 1 rule, **không có** exception kafka/aiops-engine (khác với baseline-security-context).

```yaml
spec:
  matchConstraints:
    resourceRules:
      - apiGroups: [""]
        apiVersions: ["v1"]
        resources: ["pods"]
        operations: ["CREATE", "UPDATE"]
  validations:
    - expression: >
        object.spec.containers.all(c,
          has(c.resources) && has(c.resources.requests) &&
          has(c.resources.requests.cpu) && has(c.resources.requests.memory) &&
          has(c.resources.limits) &&
          has(c.resources.limits.cpu) && has(c.resources.limits.memory)) &&
        (!has(object.spec.initContainers) || object.spec.initContainers.all(c,
          has(c.resources) && has(c.resources.requests) &&
          has(c.resources.requests.cpu) && has(c.resources.requests.memory) &&
          has(c.resources.limits) &&
          has(c.resources.limits.cpu) && has(c.resources.limits.memory)))
      message: "All containers and initContainers must define requests.cpu, requests.memory, limits.cpu, and limits.memory."
```

**Ghi chú:** đơn giản nhất trong 4 policy — pattern-match tồn tại field, CEL `has()` khớp thẳng ý nghĩa Kyverno `pattern: {resources: {requests: {cpu: "?*", ...}}}`. Không có gap nào cần xử lý riêng.

### 2.4 `custom-baseline-security-context` — 🟡 dịch được từng rule, nhưng multi-kind + exception cần thiết kế lại rõ ràng nhất trong 4 policy

Đây là policy phức tạp nhất: **8 rule**, match **9 kind** (`Pod, Deployment, StatefulSet, DaemonSet, Job, CronJob, ReplicaSet, ReplicationController, Rollout`), có 2 loại exception (kafka, aiops-engine) áp không đồng nhất giữa các rule (vd `deny-pod-run-as-user-zero`/`deny-privileged-containers` **không có** exception nào, các rule còn lại có 1 hoặc cả 2).

**Thiết kế multi-kind bằng `variables` (thay cho JMESPath fallback-chain `||` hiện tại):**

```yaml
spec:
  matchConstraints:
    resourceRules:
      - apiGroups: [""]
        apiVersions: ["v1"]
        resources: ["pods", "replicationcontrollers"]
        operations: ["CREATE", "UPDATE"]
      - apiGroups: ["apps"]
        apiVersions: ["v1"]
        resources: ["deployments", "statefulsets", "daemonsets", "replicasets"]
        operations: ["CREATE", "UPDATE"]
      - apiGroups: ["batch"]
        apiVersions: ["v1"]
        resources: ["jobs", "cronjobs"]
        operations: ["CREATE", "UPDATE"]
      - apiGroups: ["argoproj.io"]
        apiVersions: ["v1alpha1"]
        resources: ["rollouts"]
        operations: ["CREATE", "UPDATE"]
  variables:
    - name: podSpec
      expression: >
        object.kind == 'Pod' ? object.spec :
        object.kind == 'CronJob' ? object.spec.jobTemplate.spec.template.spec :
        object.spec.template.spec
    - name: containers
      expression: "variables.podSpec.containers"
    - name: initContainers
      expression: "has(variables.podSpec.initContainers) ? variables.podSpec.initContainers : []"
    - name: podSecCtx
      expression: "has(variables.podSpec.securityContext) ? variables.podSpec.securityContext : {}"
    - name: templateLabels
      expression: >
        object.kind == 'Pod' ? (has(object.metadata.labels) ? object.metadata.labels : {}) :
        object.kind == 'CronJob' ? (has(object.spec.jobTemplate.spec.template.metadata.labels) ? object.spec.jobTemplate.spec.template.metadata.labels : {}) :
        (has(object.spec.template.metadata.labels) ? object.spec.template.metadata.labels : {})
    - name: isKafka
      expression: "variables.templateLabels['app.kubernetes.io/name'] == 'kafka'"
    - name: isAiops
      expression: "variables.templateLabels['app'] == 'aiops-engine'"
```

`variables.podSpec` giả định `Rollout.spec.template.spec` cùng cấu trúc `PodTemplateSpec` như `Deployment` — **đây chính là điểm CHƯA xác nhận, xem mục 4.**

| Rule Kyverno | Exception áp dụng | CEL `validations[].expression` (dùng biến ở trên) | Độ tin cậy |
|---|---|---|---|
| `require-effective-non-root` + `require-run-as-non-root` (2 rule Kyverno hiện tại logic **trùng nhau gần như hoàn toàn** — có thể gộp làm 1 khi viết VAP, không cần dịch 2 lần) | kafka (chỉ rule đầu), aiops-engine (cả 2) | `variables.isKafka \|\| variables.isAiops \|\| variables.containers.all(c, (has(c.securityContext) && has(c.securityContext.runAsNonRoot)) ? c.securityContext.runAsNonRoot == true : (has(variables.podSecCtx.runAsNonRoot) && variables.podSecCtx.runAsNonRoot == true))` | 🟡 dịch được, nhân tiện dọn được 1 rule Kyverno dư thừa |
| `deny-pod-run-as-user-zero` | không có | `!has(variables.podSecCtx.runAsUser) \|\| variables.podSecCtx.runAsUser != 0` | 🟢 |
| `deny-container-run-as-user-zero` | kafka | `variables.isKafka \|\| (variables.containers.all(c, !has(c.securityContext) \|\| !has(c.securityContext.runAsUser) \|\| c.securityContext.runAsUser != 0) && variables.initContainers.all(c, !has(c.securityContext) \|\| !has(c.securityContext.runAsUser) \|\| c.securityContext.runAsUser != 0))` | 🟢 |
| `deny-privileged-containers` | không có | tương tự trên, check `c.securityContext.privileged == true` phải fail | 🟢 |
| `require-allow-privilege-escalation-false` | kafka, aiops-engine | `variables.isKafka \|\| variables.isAiops \|\| (containers+initContainers).all(c, has(c.securityContext) && has(c.securityContext.allowPrivilegeEscalation) && c.securityContext.allowPrivilegeEscalation == false)` | 🟢 |
| `drop-all-capabilities` | kafka, aiops-engine | `variables.isKafka \|\| variables.isAiops \|\| (containers+initContainers).all(c, has(c.securityContext) && has(c.securityContext.capabilities) && has(c.securityContext.capabilities.drop) && 'ALL' in c.securityContext.capabilities.drop)` | 🟢 |
| `require-seccomp-profile-runtime-default` | aiops-engine | `variables.isAiops \|\| variables.containers.all(c, (has(c.securityContext) && has(c.securityContext.seccompProfile) && c.securityContext.seccompProfile.type == 'RuntimeDefault') \|\| (has(variables.podSecCtx.seccompProfile) && variables.podSecCtx.seccompProfile.type == 'RuntimeDefault'))` | 🟢 |

**3 điểm thiết kế quan trọng rút ra khi dịch policy này (áp dụng chung, không chỉ riêng rule nào):**

1. **`matchConditions` không dùng được cho exception ở policy này** vì mỗi rule có tổ hợp exception khác nhau (có rule không loại trừ gì, có rule loại trừ kafka, có rule loại trừ cả 2). `matchConditions` áp cho *toàn bộ* policy — nếu dùng sẽ loại trừ nhầm cả rule không cần loại trừ (`deny-pod-run-as-user-zero`, `deny-privileged-containers`). **Bắt buộc nhúng `variables.isKafka`/`variables.isAiops` vào từng `validations[].expression`** đúng như bảng trên, không đưa lên `matchConditions`.
2. **2 rule `require-effective-non-root` và `require-run-as-non-root` nên gộp làm 1** khi viết VAP thật — logic gần như trùng lặp trong Kyverno hiện tại (khả năng là tàn dư lịch sử: `require-run-as-non-root` được thêm sau để vá bug fallback pod-level, xem `docs/docx_cdo01/mandate-05-require-run-as-non-root-pod-fallback-fix.md`, còn `require-effective-non-root` là bản gốc — cả 2 giờ check cùng 1 điều kiện). Không phải gap dịch thuật, mà là cơ hội dọn dẹp — nên ghi rõ trong PR viết VAP thật, đừng âm thầm bỏ 1 rule mà không giải thích.
3. **`ReplicationController` gần như chắc chắn không có workload thật nào dùng** trong cluster (toàn bộ 18 service TechX Corp deploy bằng `Deployment`/`Rollout`, không có service nào dùng RC — đây là API cũ, Kubernetes khuyến nghị dùng ReplicaSet/Deployment thay thế từ lâu). Giữ trong `matchConstraints.resourceRules` cho đủ tương đương Kyverno, nhưng không cần ưu tiên test kỹ nhánh này.

---

## 3. Tổng hợp mức độ dịch được — trả lời trực tiếp DoD #1 của PM-167

| ClusterPolicy | Số rule | Dịch 1:1 (🟢) | Dịch được, cần thiết kế lại (🟡) | Không dịch được (🔴) |
|---|---|---|---|---|
| `disallow-latest-tag` | 1 | 1 | 0 | 0 |
| `require-first-party-image-digest` | 1 | 0 | 1 (namespace scoping — có hướng xử lý rõ) | 0 |
| `require-resource-requests` | 1 | 1 | 0 | 0 |
| `custom-baseline-security-context` | 8 (còn 7 sau khi gộp 2 rule trùng) | 6 | 1 (multi-kind + exception, phụ thuộc `variables`, đã có hướng xử lý) | 0 (phụ thuộc kết quả mục 4 — nếu `Rollout` không đủ schema, rule này với kind `Rollout` chuyển 🔴, cần xử lý riêng) |

**Kết luận:** **không có rule nào bị chặn cứng (🔴) tại tầng CEL logic** — toàn bộ 4 policy hiện tại đều thuần regex/field-check trên object có sẵn, đúng thế mạnh của CEL. Rủi ro 🔴 duy nhất còn treo phụ thuộc **schema CRD `Rollout`** (mục 4 dưới), không phải giới hạn của CEL.

---

## 4. `Rollout` CRD — CHƯA xác nhận được, cần cluster access (yêu cầu #2 của PM-167)

**Vì sao quan trọng:** `checkout` là service duy nhất trong 18 service đi qua Argo Rollouts (Mandate #3, PR #136) thay vì Deployment thường. Nếu CRD `argoproj.io/v1alpha1 Rollout` **không có structural OpenAPI schema đầy đủ** cho `spec.template.spec.containers` (vd khai `x-kubernetes-preserve-unknown-fields: true` ở `spec.template` thay vì liệt kê rõ `PodTemplateSpec`), CEL admission cho VAP có thể:
- Vẫn truy cập được field bằng dynamic access (`object.spec.template.spec.containers`) nếu API server compile CEL ở chế độ "unstructured/dyn" — **nhưng không có type-checking lúc tạo policy**, lỗi cú pháp chỉ lộ ra lúc runtime (request thật đi qua), rủi ro cao hơn Deployment/Pod (có schema built-in, được type-check ngay khi tạo `ValidatingAdmissionPolicy`).
- Hoặc tệ hơn, nếu CRD hoàn toàn không expose field đó qua schema, CEL expression compile lỗi ngay, hoặc luôn trả `null`/lỗi runtime — khiến rule đó **âm thầm không chặn được gì cho `Rollout`**, y hệt loại bug đã từng xảy ra thật với Kyverno autogen (mục 7a báo cáo Mandate #5, PR #232) — **rủi ro lặp lại cùng 1 dạng lỗi, lần này ở tầng VAP**.

**Chưa verify được trong phiên viết doc này** — không có tunnel SSM đang mở tới cluster (`kubectl get ns techx-tf3` timeout `dial tcp [::1]:8443: connection refused` lúc viết doc, 21/07 ~12:08). Đây **không phải kết luận "không đủ schema"** — chỉ đơn giản là chưa kiểm tra được, đúng kỷ luật "verify thật, không suy đoán" đã áp dụng xuyên suốt dự án.

**Việc cần làm ngay khi có tunnel** (để trong runbook, chưa chạy):
```sh
export AWS_PROFILE=techx-new
kubectl config use-context "techx-corp-tf3-via-ssm-tunnel"

# 1. Xem CRD Rollout có structural schema cho spec.template hay preserve-unknown-fields
kubectl get crd rollouts.argoproj.io -o jsonpath='{.spec.versions[0].schema.openAPIV3Schema.properties.spec.properties.template}' | jq .

# 2. Xác nhận field cụ thể containers/initContainers/securityContext có được khai rõ không
kubectl explain rollout.spec.template.spec --recursive 2>&1 | grep -E "containers|securityContext|initContainers"

# 3. Test thật: tạo 1 ValidatingAdmissionPolicy tối giản chỉ match Rollout, validations trả về
#    object.spec.template.spec.containers.size() > 0, apply thử --dry-run=server lên 1 Rollout
#    thật (vd checkout) để xem CEL có compile + evaluate đúng không, trước khi viết bộ VAP đầy đủ.
```

**Nếu kết quả là "không đủ schema":** phương án dự phòng (chưa cần quyết định ngay, ghi lại để không bị động):
- Giữ riêng `custom-baseline-security-context` phạm vi `Rollout` ở Kyverno (Kyverno JMESPath không cần structural schema, hoạt động trên object thô) — nghĩa là **Kyverno có thể không hạ hoàn toàn về Audit cho đúng 1 rule/1 kind này**, cần bàn lại phạm vi chính xác của bước cutover ở mục 6.
- Hoặc: patch CRD `Rollout` (vendor lại từ upstream Argo Rollouts với schema đầy đủ hơn) — tốn công hơn, rủi ro hơn (đụng CRD của Argo Rollouts, ảnh hưởng cả cơ chế Mandate #3).

---

## 5. Vì sao Kyverno vẫn giữ lại (không gỡ hẳn), chỉ hạ Audit

Không phải mọi thứ Kyverno làm đều dịch được — 2 khoảng trống thật, không có hướng khắc phục bằng CEL thuần:

1. **`verifyImages`/Cosign** (PM-114, hiện Cosign mới verify off-cluster theo báo cáo Mandate #5 mục 9) — CEL không tự gọi ra ngoài (network call) để verify chữ ký số trong lúc admission. Đây là việc Kyverno vẫn cần làm, kể cả sau khi VAP lên Enforce.
2. **Background scan / PolicyReport** — VAP chỉ chặn request *mới*, không tự quét lại resource *đang chạy* để phát hiện vi phạm âm thầm lọt qua (vd do policy mới thêm sau khi resource đã tồn tại). Kyverno `background: true` vẫn có giá trị cho việc này, kể cả ở Audit.

→ Quyết định giữ Kyverno ở `Audit` (không gỡ) là đúng, không phải nửa vời: Kyverno tiếp tục làm **báo cáo/quan sát** (PolicyReport, verifyImages), còn **chặn thật tại admission** chuyển hẳn sang VAP — đúng đúng yêu cầu "native" của mentor mà không mất khả năng vốn có.

---

## 6. Rủi ro cửa sổ Audit (liên quan yêu cầu #3-4 của PM-167 — thực thi ở task/PR riêng, không phải doc này)

Doc này **chưa thực hiện** bước chuyển 4 `ClusterPolicy` từ `Enforce` sang `Audit` (đó là hành động sống trên cluster, cần làm riêng, từng policy một, verify Argo CD Synced/Healthy + storefront 200 sau mỗi bước — đúng kỷ luật cutover đã dùng ở Mandate #5 gốc, xem `docs/docx_cdo01/enforce-cutover-20260718.md`). Ghi nhận rõ ràng rủi ro sẽ áp dụng khi bước đó được thực hiện, để không ai hiểu nhầm đây là "rollback bảo mật":

- **Trong lúc Kyverno ở `Audit` và VAP chưa `Enforce` (hoặc chưa tồn tại)**, cluster **không có gì chặn thật** tại admission cho 4 nhóm rule: container chạy root, image `latest`/không pin digest, thiếu resource request/limit đều **apply được thành công**, chỉ bị ghi nhận trong `PolicyReport` (Kyverno Audit) — không chặn.
- `verifyImages`/Cosign (nếu đã bật ở phạm vi khác PM-114) **không bị ảnh hưởng** bởi việc hạ `validationFailureAction` của 4 policy này — vẫn còn hiệu lực nếu tồn tại độc lập.
- **Khuyến nghị bắt buộc:** khoảng thời gian này phải **ngắn nhất có thể** — lý tưởng là hạ Audit và lên VAP Enforce trong cùng 1 buổi làm việc, không để treo qua đêm/qua nhiều ngày. Nếu vì lý do nào đó phải treo lâu (vd đang chờ xác nhận CRD `Rollout` ở mục 4), cân nhắc **chỉ hạ Audit cho 3 policy đã 🟢/🟡 rõ ràng** (`disallow-latest-tag`, `require-first-party-image-digest`, `require-resource-requests`), giữ `custom-baseline-security-context` ở `Enforce` cho tới khi mục 4 được giải quyết — vì đây là policy chặn root/privileged, rủi ro cao nhất nếu mất enforcement.
- PR/commit thực hiện bước hạ Audit **phải ghi rõ trong message**: "tạm thời, phục vụ chuyển đổi sang VAP (PM-166/167), không phải rollback bảo mật" + link doc này — đúng yêu cầu #4 của PM-167.

---

## 7. Trả lời trực tiếp DoD của PM-167

- [x] **Có bảng ánh xạ đầy đủ: mỗi rule Kyverno → biểu thức CEL tương đương hoặc lý do không dịch được.** → mục 2 (đủ 4 policy, 11 rule gốc/10 sau gộp), mục 3 (bảng tổng hợp).
- [ ] **Xác nhận rõ CRD `Rollout` có dịch được sang CEL hay cần xử lý riêng.** → **CHƯA xác nhận được** — cần tunnel SSM sống, lệnh cụ thể đã ghi ở mục 4, chưa chạy. **Đây là việc còn mở duy nhất chặn PM-167 đóng hoàn toàn.**
- [ ] **Cả 4 ClusterPolicy đã ở `Audit`, storefront vẫn 200, Argo CD vẫn Synced/Healthy.** → **Chưa thực hiện** — nằm ngoài phạm vi doc phân tích này, là task hành động riêng (xem mục 6 để biết trình tự khuyến nghị).
- [ ] **Có ghi chú rõ ràng (PR + Jira comment) về rủi ro tạm thời mất enforcement thật trong lúc chuyển đổi.** → nội dung đã chuẩn bị sẵn ở mục 6, sẽ dùng khi tạo PR/comment thật lúc thực hiện bước Audit.

---

## 8. Việc tiếp theo (theo thứ tự)

1. Mở tunnel SSM, chạy 3 lệnh ở mục 4 — xác nhận schema `Rollout`. Đây là input bắt buộc trước khi viết VAP YAML thật cho `custom-baseline-security-context`.
2. Viết `ValidatingAdmissionPolicy` + `ValidatingAdmissionPolicyBinding` thật (bắt đầu `validationActions: [Audit]` trước, đúng kỷ luật cutover cũ), test bằng đúng fixture `docs/evidence/mandate-05/rejection-demo/*.yaml`.
3. Thực hiện bước hạ `Enforce → Audit` cho Kyverno theo trình tự khuyến nghị ở mục 6 (ưu tiên hạ trước 3 policy 🟢/🟡 rõ ràng, giữ `custom-baseline-security-context` lại nếu mục 4 chưa xong).
4. Cutover VAP `Audit → Deny` từng policy một, verify Synced/Healthy + storefront 200 — lặp lại đúng kỷ luật đã dùng ở `enforce-cutover-20260718.md`.
5. Cập nhật ADR 0010 + báo cáo mentor-facing (`mandate-05-runtime-hardening-report.md`) phản ánh kiến trúc mới: VAP = enforcement chính, Kyverno = audit/report/Cosign-verify.

---

## 9. Tài liệu liên quan

- Epic: PM-166. Task này: PM-167.
- Nguồn 4 policy đang audit: `gitops/policies/kyverno/{baseline-security-context,disallow-latest-tag,require-first-party-image-digest,require-resource-requests}.yaml`.
- Bối cảnh autogen gap từng gặp với Kyverno (tham khảo cách xử lý `Rollout` tay): PR #232, mục 7a `docs/docx_cdo01/mandate-05-runtime-hardening-report.md`.
- Bug fallback pod-level từng vá cho `require-run-as-non-root`: `docs/docx_cdo01/mandate-05-require-run-as-non-root-pod-fallback-fix.md`.
- Cutover Audit→Enforce gốc (mẫu quy trình sẽ lặp lại cho VAP): `docs/docx_cdo01/enforce-cutover-20260718.md`.
- Exception register hiện có (kafka, aiops-engine): `docs/evidence/mandate-05/exception-register.yaml`.
