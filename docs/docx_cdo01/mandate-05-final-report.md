# Mandate 5 — Báo cáo tổng hợp cuối cùng 

**Ngày viết:** 18/07/2026, **cập nhật lần cuối:** 20/07/2026 (mandate deadline gốc: 17/07/2026)
**Mục đích file này:** để bất kỳ ai ở TF3 đọc là hiểu ngay mandate yêu cầu gì, team đã làm gì, làm ở đâu trong code, và lệnh nào để tự verify lại — không cần hỏi lại người đã làm.

**Nguồn:** mandate gốc `/Users/tan/Desktop/notes-for-phase3/xbrain-learners/phase3/mandates/MANDATE-05-runtime-hardening.md`, đối chiếu Jira (PM-92, PM-101, PM-104, PM-110-114), verify trực tiếp trên cluster sống `techx-corp-tf3` (account `197826770971`).

**Thay đổi lớn nhất từ 18/07:** cả 3 policy `custom-baseline-security-context`, `disallow-latest-tag`, `require-resource-requests` đã chuyển từ chỉ áp `namespace: techx-tf3` sang **áp toàn cluster** (trừ `kube-system`/`kyverno` — đã bị loại trừ sẵn ở tầng webhook). Chi tiết: mục "Mở rộng phạm vi ra toàn cluster" bên dưới.

---

## Tóm tắt trạng thái

| Yêu cầu mandate | Trạng thái | Ghi chú |
|---|---|---|
| 1. Không container nào chạy root | ✅ Enforce, **toàn cluster** | Gap autogen đã fix (PR #232); bug rule `require-run-as-non-root` thiếu fallback cấp Pod đã fix 20/07 |
| 2. Không xài image trôi, pin digest | ✅ Enforce, **toàn cluster** | 0 vi phạm thật |
| 3. Mọi workload có resource request/limit | ✅ Enforce, **toàn cluster** | `argocd`/`kyverno`/`argo-rollouts` đã vá đủ resource trước khi mở rộng |
| 4. Enforce tự động tại admission | ✅ Cả 4 `ClusterPolicy` đã Enforce | Cutover có kiểm soát, từng policy một |
| "Phải nộp": demo rejection cho mentor | ⏳ Chưa làm — mới tự test nội bộ | Xem mục "Demo video" ngay dưới |
| "Phải nộp": ADR ký tên | 🟡 Đã viết, chưa có chữ ký chính thức | `docs/adr/0010-mandate-05-runtime-hardening.md` |

**2 exception còn hiệu lực:** `kafka` (init-container cần root để `chown` PVC) và `aiops-engine` (workload AIO02, ngoài GitOps repo này) — chi tiết `docs/evidence/mandate-05/exception-register.yaml`.

**Trạng thái Git:** 3 file policy cluster-wide + bản vá `require-run-as-non-root` đã merge vào `main` (PR #261, 19/07) — khớp với trạng thái đang chạy live trên cluster.

---

## Demo video (cho mentor / lưu bằng chứng)

Lệnh chạy cả 4 manifest vi phạm cùng lúc — dùng để quay video chứng minh admission chặn thật (dry-run, không tạo resource thật nên an toàn chạy nhiều lần):

```sh
for f in docs/evidence/mandate-05/rejection-demo/*.yaml; do
  echo "=== $f ==="
  kubectl apply --dry-run=server -f "$f"
  echo
done
```

Cả 4 lệnh phải báo `admission webhook "validate.kyverno.svc-fail" denied the request`.

**Link video demo:** _[dán link vào đây]_

---

## Yêu cầu #1 — Không container nào chạy root

> *"Buộc `runAsNonRoot`, drop mấy capability thừa - chỉ giữ đúng cái thật sự cần."*

### 1.1. Đã làm gì

- **Pod Security Admission (PSA)** bật ở `techx-tf3`, mức `baseline`, chế độ `audit`+`warn` (chặn thật giao cho Kyverno).
- **`securityContext` baseline** cho từng container: `runAsNonRoot: true`, `allowPrivilegeEscalation: false`, `capabilities.drop: ["ALL"]`, `seccompProfile.type: RuntimeDefault`. Áp qua 2 cơ chế: component TF3 tự viết (`components.<name>.securityContext`) và subchart dependency (field riêng từng chart upstream).
- **Vá base image** cho `currency`/`llm`/`product-reviews` (thiếu `USER` directive trong Dockerfile Alpine).
- **Kyverno `ClusterPolicy` `custom-baseline-security-context`** — 8 rule, admission-time, **áp toàn cluster** (trừ kube-system/kyverno).

### 1.2. Ở đâu trong code

| Thành phần | File |
|---|---|
| Nhãn PSA | `gitops/infrastructure/namespace-techx-tf3.yaml` |
| securityContext | `techx-corp-chart/values.yaml` + `deploy/values-prod.yaml` |
| Dockerfile vá base image | `techx-corp-platform/src/{currency,llm,product-reviews}/Dockerfile` |
| Kyverno policy | `gitops/policies/kyverno/baseline-security-context.yaml` |
| Exception | `docs/evidence/mandate-05/exception-register.yaml` |

### 1.3. Lệnh verify

```sh
# PSA labels
kubectl get ns techx-tf3 -o jsonpath='{.metadata.labels}'
# -> phải có pod-security.kubernetes.io/audit=baseline, .../warn=baseline

# Trạng thái Kyverno
kubectl get clusterpolicy custom-baseline-security-context -o jsonpath='{.spec.validationFailureAction} {.status.conditions[?(@.type=="Ready")].status}'
# -> "Enforce True"

# Quét baseline TOÀN CLUSTER (trừ kube-system/kyverno) — container + initContainer,
# fallback cấp Pod đúng như Kyverno thật đánh giá
kubectl get pods -A -o json > /tmp/allpods.json
python3 - << 'EOF'
import json
pods = json.load(open('/tmp/allpods.json'))
bad = []
total = 0
for p in pods['items']:
    if p['metadata']['namespace'] in ('kube-system', 'kyverno'):
        continue
    pod_sc = p['spec'].get('securityContext') or {}
    pod_seccomp = (pod_sc.get('seccompProfile') or {}).get('type')
    pod_nonroot = pod_sc.get('runAsNonRoot')
    for c in p['spec'].get('containers', []) + p['spec'].get('initContainers', []):
        total += 1
        sc = c.get('securityContext') or {}
        ape = sc.get('allowPrivilegeEscalation')
        caps = (sc.get('capabilities') or {}).get('drop', [])
        seccomp = (sc.get('seccompProfile') or {}).get('type') or pod_seccomp
        nonroot = sc.get('runAsNonRoot')
        if nonroot is None:
            nonroot = pod_nonroot
        if not (ape is False and 'ALL' in caps and seccomp == 'RuntimeDefault' and nonroot is True):
            bad.append((p['metadata']['namespace'], p['metadata']['name'], c['name']))
print(f"{total - len(bad)}/{total} dat baseline")
print("Con thieu (ky vong: chi aiops-engine + kafka init-kafka-data):", bad)
EOF

# Demo chặn thật
kubectl apply --dry-run=server -f docs/evidence/mandate-05/rejection-demo/bad-root.yaml
```

### 1.4. Lịch sử fix (đã đóng)

`custom-baseline-security-context` từng không có autogen rule cho `Deployment/StatefulSet/DaemonSet/Job/CronJob` (chỉ bảo vệ `Pod` trần) — **đã fix PR #232** bằng cách khai tường minh cả 9 kind (kể cả `Rollout`, thứ autogen gốc của Kyverno không bao giờ cover được) thay vì phụ thuộc autogen. Sau đó, rule `require-run-as-non-root` (1 trong 8 rule) bị phát hiện thiếu fallback cấp Pod, gây FAIL nhầm cho workload chỉ khai `runAsNonRoot` ở Pod (không phải lỗ hổng bảo mật thật) — **đã fix 20/07**, bằng chứng đầy đủ ở `docs/docx_cdo01/mandate-05-require-run-as-non-root-pod-fallback-fix.md`.

---

## Yêu cầu #2 — Không xài image trôi, cấm tag "latest", pin theo digest

> *"Cấm tag kiểu `latest`; pin theo digest hoặc tag cố định để biết chính xác đang chạy version nào."*

### 2.1. Đã làm gì

**CI (`.github/workflows/build-push-ecr.yml`):** mọi image gắn tag duy nhất `<git-short-sha>-<run-id>-<service>` (không bao giờ `latest`); sau khi push, tự tra lại ECR (`aws ecr describe-images`) lấy đúng digest thật, validate bằng regex trước khi chấp nhận; ECR bật tag immutability.

**Deploy (PM-113 pipeline):** `scripts/ci/update-image-overrides.py` ghi đúng dòng `imageOverride.digest` vào `deploy/values-prod.yaml`; `scripts/ci/verify-rendered-images.py` render `helm template` thật để verify (bắt được cả lỗi tráo digest giữa 2 service). Không commit thẳng `main` — luôn qua PR.

**Admission (Kyverno):** `disallow-latest-tag` (regex chặn `:latest`/implicit-latest) + `require-first-party-image-digest` (bắt buộc `@sha256:` cho image ECR `techx-corp`) — **cả 2 áp toàn cluster**.

### 2.2. Ở đâu trong code

| Thành phần | File |
|---|---|
| Build + resolve digest | `.github/workflows/build-push-ecr.yml` (job `build-scan`) |
| Ghi digest | `scripts/ci/update-image-overrides.py` |
| Verify render | `scripts/ci/verify-rendered-images.py` |
| Kyverno cấm latest | `gitops/policies/kyverno/disallow-latest-tag.yaml` |
| Kyverno bắt buộc digest | `gitops/policies/kyverno/require-first-party-image-digest.yaml` |

### 2.3. Lệnh verify

```sh
kubectl get clusterpolicy disallow-latest-tag require-first-party-image-digest \
  -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.spec.validationFailureAction}{" "}{.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}'
# -> ca 2 phai "Enforce True"

# Quet image TOAN CLUSTER (tru kube-system/kyverno) - khong con :latest, first-party phai co digest
kubectl get pods -A -o jsonpath='{range .items[*]}{.metadata.namespace}{" "}{range .spec.containers[*]}{.image}{"\n"}{end}{end}' \
  | awk '$1!="kube-system" && $1!="kyverno" {print $2}' | sort -u > /tmp/all_images.txt
grep -E ':latest$|^[^@:/]+$' /tmp/all_images.txt && echo "CO VI PHAM :latest" || echo "OK - khong con :latest"
grep '197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp' /tmp/all_images.txt | grep -v '@sha256:' && echo "CO VI PHAM thieu digest" || echo "OK - first-party deu co digest"

# Demo chặn thật (2 lỗi khác nhau: :latest vs thiếu digest với tag cố định)
kubectl apply --dry-run=server -f docs/evidence/mandate-05/rejection-demo/bad-latest-image.yaml
kubectl apply --dry-run=server -f docs/evidence/mandate-05/rejection-demo/bad-digest.yaml
```

### 2.4. Exception

`kafka` — đã tự đạt digest thật, exception trong register coi như dư nhưng chưa gỡ khỏi hồ sơ (không ảnh hưởng chức năng).

---

## Yêu cầu #3 — Mọi workload phải định nghĩa resource request/limit

> *"Để trống là một pod có thể ngốn sạch resources của node rồi kéo sập cả cluster."*

### 3.1. Đã làm gì

Mọi container/sidecar/initContainer khai tường minh đủ 4 field `requests.cpu/memory`, `limits.cpu/memory` — không dựa default ngầm. `LimitRange techx-limits` (`techx-tf3`) là lưới an toàn cho Pod tạo trực tiếp (edge-case, không dùng cho workload thật). **Kyverno `require-resource-requests` áp toàn cluster.**

### 3.2. Ở đâu trong code

| Thành phần | File |
|---|---|
| Resource declaration | `techx-corp-chart/values.yaml` + `deploy/values-prod.yaml` |
| ArgoCD (vendor riêng, không qua chart) | `gitops/bootstrap/argocd/kustomization.yaml` — xem runbook `docs/runbooks/argocd-resource-limits-kustomize-adoption.md` |
| Kyverno/argo-rollouts | `gitops/apps/{kyverno,argo-rollouts}-app.yaml` |
| Kyverno policy | `gitops/policies/kyverno/require-resource-requests.yaml` |

### 3.3. Lệnh verify

```sh
kubectl get clusterpolicy require-resource-requests -o jsonpath='{.spec.validationFailureAction} {.status.conditions[?(@.type=="Ready")].status}'
# -> "Enforce True"

# Quet resources TOAN CLUSTER (tru kube-system/kyverno), ca container lan initContainer
kubectl get pods -A -o json > /tmp/allpods.json
python3 - << 'EOF'
import json
pods = json.load(open('/tmp/allpods.json'))
bad = []
total = 0
for p in pods['items']:
    if p['metadata']['namespace'] in ('kube-system', 'kyverno'):
        continue
    for c in p['spec'].get('containers', []) + p['spec'].get('initContainers', []):
        total += 1
        res = c.get('resources', {})
        req, lim = res.get('requests', {}), res.get('limits', {})
        if not (req.get('cpu') and req.get('memory') and lim.get('cpu') and lim.get('memory')):
            bad.append((p['metadata']['namespace'], p['metadata']['name'], c['name']))
print(f"{total - len(bad)}/{total} du 4 field. Con thieu:", bad)
EOF

# Demo chặn thật — BẮT BUỘC dùng Deployment, KHÔNG Pod trần (xem mục 3.4)
kubectl apply --dry-run=server -f docs/evidence/mandate-05/rejection-demo/bad-missing-resources.yaml
```

### 3.4. Vì sao demo phải dùng Deployment, không dùng Pod trần

Pod trần tạo trực tiếp trong `techx-tf3` được `LimitRange techx-limits` **tự động điền default** trước khi Kyverno kịp đánh giá (mutating admission chạy trước validating webhook) — nên Pod trần thiếu resources **không bị chặn**, dù Deployment/StatefulSet (100% cách production thật deploy) vẫn bị chặn đúng. Không phải lỗi — `bad-missing-resources.yaml` đã cố ý dùng `kind: Deployment`.

---

## Yêu cầu #4 — Enforce tự động tại admission, không rà tay

> *"Đẩy mấy luật trên vào admission (policy-as-code): manifest vi phạm bị từ chối ngay lúc apply... đi từ audit sang enforce có kiểm soát."*

### 4.1. Đã làm gì

- Cài Kyverno qua GitOps (`gitops/apps/kyverno-app.yaml`), 4 controller Running.
- 4 `ClusterPolicy` ở `Audit` trước (PR #194) → rà soát + vá dần vi phạm thật nhiều ngày → dọn exception thừa (11 → 2) → **chuyển từng policy 1 sang `Enforce`**, mỗi bước verify ArgoCD Synced/Healthy + storefront HTTP 200.
- `docs/adr/0010-mandate-05-runtime-hardening.md` ghi quyết định Audit/Enforce, exception, rollback.

### 4.2. Ở đâu trong code

| Thành phần | File |
|---|---|
| Cài Kyverno | `gitops/apps/kyverno-app.yaml` |
| 4 ClusterPolicy | `gitops/policies/kyverno/*.yaml` |
| Exception register | `docs/evidence/mandate-05/exception-register.yaml` |
| ADR | `docs/adr/0010-mandate-05-runtime-hardening.md` |
| Bộ test Kyverno CLI | `tests/kyverno/mandate-05/` |
| 4 manifest demo rejection | `docs/evidence/mandate-05/rejection-demo/*.yaml` |

### 4.3. Lệnh verify

```sh
# Cả 4 policy phải Enforce + Ready
kubectl get clusterpolicy -o jsonpath='{range .items[*]}{.metadata.name}{"  action="}{.spec.validationFailureAction}{"  ready="}{.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}'

# PolicyReport sạch — CHỈ tính resource đang thật sự sống (loại ReplicaSet cũ đã
# chết, bẫy đã gặp nhiều lần: xoá PolicyReport không giúp gì vì Kyverno tự quét
# lại từ ReplicaSet cũ còn tồn tại trong etcd)
kubectl get pods -A -o json > /tmp/allpods.json
kubectl get rs -A -o json > /tmp/allrs.json
kubectl get policyreports -A -o json > /tmp/policyreports.json
python3 - << 'EOF'
import json
pods = json.load(open('/tmp/allpods.json'))
rs = json.load(open('/tmp/allrs.json'))
reports = json.load(open('/tmp/policyreports.json'))
live_pods = {(p['metadata']['namespace'], p['metadata']['name']) for p in pods['items']}
active_rs = {(r['metadata']['namespace'], r['metadata']['name']) for r in rs['items'] if r['spec'].get('replicas', 0) > 0}
found = False
for r in reports['items']:
    s = r.get('scope', {})
    ns, name, kind = s.get('namespace'), s.get('name'), s.get('kind')
    if ns in ('kube-system', 'kyverno'):
        continue
    if kind == 'Pod':
        is_live = (ns, name) in live_pods
    elif kind == 'ReplicaSet':
        is_live = (ns, name) in active_rs
    else:
        is_live = True
    if not is_live:
        continue
    for res in r.get('results', []):
        if res.get('result') == 'fail':
            found = True
            print(ns, name, kind, res.get('policy'), res.get('rule'))
if not found:
    print("0 fail that")
EOF

# Chay lai bo test Kyverno CLI (can cai `kyverno` CLI)
kyverno test tests/kyverno/mandate-05/
```

Demo rejection thật cho mentor: xem mục "Demo video" ở đầu file.

### 4.4. PM-101 (Trivy + Cosign) — hỗ trợ yêu cầu #2, không phải core requirement

Trivy chặn CI nếu image có CVE CRITICAL/HIGH (scan trước và sau push). Cosign keyless (GitHub OIDC) ký mọi digest ngay sau push — verify **20/20 digest first-party đang chạy sống** (18/07):

```sh
aws ecr get-login-password --region ap-southeast-1 | docker login --username AWS --password-stdin 197826770971.dkr.ecr.ap-southeast-1.amazonaws.com
kubectl get pods -A -o jsonpath='{range .items[*]}{range .spec.containers[*]}{.image}{"\n"}{end}{end}' \
  | grep 'techx-corp@sha256:' | sort -u | while read -r img; do
    cosign verify --certificate-identity-regexp="https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel" \
      --certificate-oidc-issuer="https://token.actions.githubusercontent.com" "$img" >/dev/null 2>&1 \
      && echo "PASS $img" || echo "FAIL $img"
  done
```

**Chưa làm (PM-114, không phải core):** Kyverno `verifyImages` Cosign tại admission-time — cả PM-101/PM-104 ghi rõ đây là phần nâng cao/tuỳ chọn.

---

## Mở rộng phạm vi ra toàn cluster (19-20/07)

**Phát hiện quyết định hướng đi:** webhook `validate.kyverno.svc-fail` đã tự loại trừ `kube-system`/`kyverno` ở tầng webhook — "mở rộng toàn cluster" chỉ thật sự liên quan 3 namespace TF3 tự cài qua GitOps: `argocd`, `external-secrets`, `argo-rollouts`. Quét trước khi mở: baseline + no-latest-tag đã sạch sẵn; `require-resource-requests` có vi phạm thật ở `argocd` (9/9 container không khai gì), `kyverno`/`argo-rollouts` (thiếu `limits.cpu`) — cần vá trước.

**Vá `argocd`** (không qua Helm/GitOps repo này, `kubectl apply` thô 1 lần) — chọn hướng B: vendor `install.yaml` gốc (verify `kubectl diff` = 0 khác biệt trước khi patch), Kustomize overlay thêm resources cho 7 container + 3 initContainer (`copyutil`×2, `secret-init` — phát hiện bổ sung khi quét lại lần 2), viết `gitops/apps/argocd-self-app.yaml` để ArgoCD tự quản lý chính nó. Quy trình đầy đủ: `docs/runbooks/argocd-resource-limits-kustomize-adoption.md`.

**⚠️ Sự cố thật:** lần đầu `argocd-self` tự sync, `argocd-application-controller` **bị OOMKilled** vì `limits.memory: 512Mi` ước lượng quá thấp (diff toàn bộ 59 resource + CRD `Application`/`AppProject` khá nặng). Đã vá lên `1Gi`. Bài học kép: (1) đúng dạng rủi ro "tự-deadlock" đã cảnh báo trước khi làm hướng B2 — ArgoCD chết thì không có gì tự sync để cứu nó; (2) sửa tay cluster mà chưa sửa Git thì `syncPolicy.automated.selfHeal` của chính Application đó **tự động revert lại** — phải tạm tắt `automated` trong lúc sửa Git rồi mới bật lại. Bài học lặp lại y hệt lần 2 qua Application `kyverno-policies` khi vá bug `require-run-as-non-root`.

**Vá `kyverno`/`argo-rollouts`:** thêm `limits.cpu` — `admission-controller: 1000m` (để rộng, vì admission webhook chạy đồng bộ trên đường deploy toàn cluster, CPU throttle lúc burst có thể gây timeout webhook); `background/reports-controller: 500m`; `cleanup-controller: 200m`; `argo-rollouts: 300m`.

**Bug `require-run-as-non-root`:** rule chỉ đọc `runAsNonRoot` cấp container, thiếu fallback cấp Pod — gây **chặn thật** (không chỉ báo sai) cho `argo-rollouts`/`argocd-redis`/`argocd-notifications-controller` (chỉ khai ở cấp Pod, hợp lệ — rule song song `require-effective-non-root` đã xác nhận PASS). Đã vá thêm 3 vế fallback theo đúng pattern đã dùng ở rule kia. Bằng chứng đầy đủ: `docs/docx_cdo01/mandate-05-require-run-as-non-root-pod-fallback-fix.md`.

**Phát hiện phụ:** `kubectl get policyreport -A` có thể hiện rất nhiều FAIL "ma" từ ReplicaSet cũ đã chết (0 replica, còn sót trong etcd) — xoá PolicyReport không giúp gì, phải lọc `spec.replicas > 0` (script ở mục 4.3). Có 1 ReplicaSet rác thật (`m5-t20`, `techx-tf3`, `busybox:latest`, không owner, 0 pod) chưa ai xoá.

Chi tiết đầy đủ + số liệu quét: `docs/docx_cdo01/mandate-05-gap-analysis-20260718.md` mục 8, `docs/docx_cdo01/mandate-05-cluster-wide-scope-expansion.md`.

---

## Ngoại lệ đang còn hiệu lực

| ID | Workload | Policy | Lý do | Chủ sở hữu |
|---|---|---|---|---|
| `m05-baseline-kafka-init-chown` | `kafka` (init `init-kafka-data`) | `custom-baseline-security-context` | Cần root để `chown` PVC trước khi `kafka` (non-root) khởi động | CDO02 |
| `m05-baseline-aiops-engine-runtime` | `aiops-engine` | `custom-baseline-security-context` | Deployment ngoài GitOps repo này, chưa có securityContext | AIO02 |

---

## Việc còn tồn đọng

1. ~~Rejection ngay lúc apply Deployment~~ — xong, PR #232.
2. ~~Mở rộng 3 policy ra toàn cluster~~ — xong, apply + verify sống 20/07.
3. Lịch demo thật với mentor — mandate yêu cầu mentor tự tay `kubectl apply`, chưa phải bàn giao chính thức.
4. Ký chính thức ADR 0010.
5. Chốt dứt điểm 2 exception còn lại (`aiops-engine` cần AIO02 tự thêm securityContext; `kafka` cần đánh giá non-root ownership nếu muốn gỡ hẳn).
6. Dọn ReplicaSet rác `m5-t20` (cần người xác nhận nguồn gốc trước khi xoá).
7. *(Không gấp)* PM-114 — Kyverno `verifyImages` Cosign, vẫn "To Do".
8. *(Không gấp)* ArgoCD hiện ở mức "vendor + patch" (hướng B) — có thể cân nhắc B2 đầy đủ hơn sau.

---

## Phụ lục — PR liên quan (theo thời gian)

`#139` (rebrand) → `#145` (mandate-5 gộp) → `#148` (PM-101) → `#194` (4 policy Audit) → `fe2adde`/`#207` (flagd/postgresql securityContext) → `#208` (fix Kyverno sync) → `#209` (aiops exception) → `#222` (flagd-ui resources) → `#223` (dọn exception + fix scope) → `#224` (Enforce resources) → `#225` (fix bug pattern) → `#226` (Enforce disallow-latest-tag) → `#227` (Enforce digest) → `#229` (fix JMESPath) → `#230` (Enforce baseline) → `#231` (closeout docs) → `#232` (fix autogen gap) → `#256` (resources argocd/kyverno/argo-rollouts + OOMKill incident) → `#257` (fix `512Mi→1Gi`) → `#258` (3 policy → cluster-wide, 19/07) → `revert policies` (tạm lùi về `techx-tf3` để review) → `#261` (fix `require-run-as-non-root` + mở lại cluster-wide lần 2, đã merge 19/07).

**Tài liệu chi tiết:** `docs/docx_cdo01/mandate-05-gap-analysis-20260718.md`, `docs/docx_cdo01/mandate-05-cluster-wide-scope-expansion.md`, `docs/docx_cdo01/mandate-05-require-run-as-non-root-pod-fallback-fix.md`, `docs/runbooks/argocd-resource-limits-kustomize-adoption.md`.
