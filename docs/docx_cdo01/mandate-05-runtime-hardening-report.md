# Mandate #5 — Báo cáo Runtime Admission Hardening (chặn root / image trôi / thiếu resource ngay lúc admission)

**Directive:** Mandate 05 — Runtime Admission Hardening (xem `docs/adr/0010-mandate-05-runtime-hardening.md`)<br>
**Ngày Audit → Enforce cutover (phạm vi `techx-tf3`):** 18/07/2026<br>
**Ngày mở rộng Enforce ra toàn cluster + vá bug fallback pod-level:** 19-20/07/2026<br>
**Nhóm thực hiện:** CDO01 (Security, chủ trì) phối hợp CDO02 (resource/reliability cho ArgoCD/Kyverno/argo-rollouts khi mở rộng phạm vi)<br>
**Người xác nhận/chứng kiến (mentor):** _(điền)_<br>
**Video demo:** _(dán link vào đây)_<br>
**Kết quả:** **PASS — 4 `ClusterPolicy` Kyverno đều `Enforce`/`Ready`, áp dụng toàn cluster (trừ `kube-system`/`kyverno`, loại trừ ở tầng webhook), chặn thật ngay lúc admission — không phải báo cáo sau.**

---

## 1. Mục tiêu & phạm vi

**Chứng minh:** mọi workload trong cluster — không chỉ lúc code review — bị **chặn ngay tại API server** nếu:
1. container chạy bằng root,
2. image dùng tag `latest`/trôi (không pin digest cho image nội bộ),
3. thiếu khai báo `requests`/`limits` CPU-memory.

Và việc chặn này là **policy-as-code tại admission**, không phải rà tay hay CI-only.

**Phạm vi:**
- **First-party**: 18 workload ứng dụng của `techx-tf3` (chart chính TechX Corp).
- **Toàn cluster** (mở rộng 19-20/07): `argocd`, `argo-rollouts`, `external-secrets` cũng bị áp — chỉ `kube-system`/`kyverno` được loại trừ, và loại trừ này nằm ở **tầng webhook** (`validate.kyverno.svc-fail`), không phải do policy "bỏ sót".
- **2 exception có kiểm soát**, đăng ký công khai trong `docs/evidence/mandate-05/exception-register.yaml` (chi tiết mục 3).

## 2. Cơ sở kỹ thuật (đã build trước demo)

| Lớp | Cơ chế | Bằng chứng |
|---|---|---|
| Baseline OS | Pod Security Admission `baseline`, mode `audit`+`warn` (chặn thật giao cho Kyverno) | `gitops/infrastructure/namespace-techx-tf3.yaml` |
| securityContext | `runAsNonRoot`, `allowPrivilegeEscalation:false`, `capabilities.drop:[ALL]`, `seccompProfile:RuntimeDefault` cho từng container | `techx-corp-chart/values.yaml`, `deploy/values-prod.yaml` |
| Base image | Vá `USER` directive thiếu ở `currency`/`llm`/`product-reviews` (Alpine) | Dockerfile từng service |
| **Admission — 4 `ClusterPolicy` Kyverno, `Enforce`, toàn cluster** | `custom-baseline-security-context` (8 rule: non-root, no-privileged, drop-caps, seccomp...) · `disallow-latest-tag` · `require-first-party-image-digest` · `require-resource-requests` | `gitops/policies/kyverno/*.yaml` |

**Cutover có kiểm soát:** mỗi policy đi `Audit` trước, rà + vá vi phạm thật, dọn exception thừa (11→2), rồi mới chuyển `Enforce` **từng cái một**, verify Argo CD Synced/Healthy + storefront `200` sau mỗi bước. Bằng chứng đầy đủ ngày cutover 18/07: `docs/docx_cdo01/enforce-cutover-20260718.md`.

## 3. Chuẩn bị & pre-flight trước khi mở rộng ra toàn cluster

Trước khi bật `require-resource-requests` cho `argocd`/`kyverno`/`argo-rollouts` (namespace do TF3 tự cài, ngoài chart chính), đã verify không có gì thiếu resource — tránh policy tự chặn ngay chính hạ tầng vận hành:

- [x] `argocd` (7 Deployment/StatefulSet + 3 initContainer) — vendor lại `install.yaml` gốc (verify `kubectl diff` = 0 khác biệt trước khi patch), thêm `requests`/`limits` qua Kustomize overlay. Chi tiết đầy đủ: `docs/runbooks/argocd-resource-limits-kustomize-adoption.md`.
- [x] `kyverno` (4 controller) — bổ sung `limits.cpu` (chart mặc định thiếu, chỉ có `limits.memory`) theo đề xuất kỹ thuật đã review: `admissionController: 1000m` (để rộng vì webhook chạy đồng bộ trên đường deploy toàn cluster, CPU throttle có thể làm timeout webhook 10s và tê liệt deploy cả cụm); `backgroundController`/`reportsController: 500m`; `cleanupController: 200m`. File: `gitops/apps/kyverno-app.yaml`.
- [x] `argo-rollouts` — thêm `limits.cpu: 300m` (đã có sẵn requests + limits.memory). File: `gitops/apps/argo-rollouts-app.yaml`.
- [x] PolicyReport sạch, loại trừ noise từ ReplicaSet cũ đã chết (0 replica, còn sót trong etcd — không phải vi phạm thật, chi tiết mục 7).

**Exception đang có hiệu lực (đăng ký công khai, có owner + review date, không phải "quên"):**

| ID | Workload | Lý do | Owner | Review |
|---|---|---|---|---|
| `m05-baseline-kafka-init-chown` | `kafka` init-container | Cần root để `chown` PVC trước khi broker (non-root) khởi động | CDO02 | 24/07/2026 |
| `m05-baseline-aiops-engine-runtime` | `aiops-engine` | Ngoài GitOps repo này, chưa có securityContext hardening | AIO02 | 24/07/2026 |

## 4. Quy trình demo đã thực hiện (khớp video)

4 manifest vi phạm, mỗi manifest đúng 1 lỗi, `kind: Deployment` (không dùng Pod trần — lý do ở mục 5):

```sh
export AWS_PROFILE=techx-new
for f in docs/evidence/mandate-05/rejection-demo/*.yaml; do
  echo "=== $f ==="
  kubectl apply --dry-run=server -f "$f"
  echo
done
```

| File | Vi phạm cố ý |
|---|---|
| `bad-root.yaml` | Container không set `runAsNonRoot` |
| `bad-latest-image.yaml` | Image dùng tag `:latest` |
| `bad-digest.yaml` | Image ECR nội bộ dùng tag cố định thay vì `@sha256:` digest |
| `bad-missing-resources.yaml` | Container không khai `requests`/`limits` |

## 5. Kết quả

Cả 4 lệnh đều bị từ chối ngay tại admission (`server-side dry-run`, không tạo resource thật):

```
Error from server: admission webhook "validate.kyverno.svc-fail" denied the request:
custom-baseline-security-context: require-run-as-non-root: 'validation failure: ...'   # bad-root.yaml
disallow-latest-tag: require-explicit-non-latest-image-reference: '...'                # bad-latest-image.yaml
require-first-party-image-digest: ...                                                  # bad-digest.yaml
require-resource-requests: require-cpu-memory-requests-limits: '...'                   # bad-missing-resources.yaml
```

**Vì sao 4 manifest demo dùng `kind: Deployment`, không dùng Pod trần:** `LimitRange techx-limits` trong `techx-tf3` tự động điền default resource cho Pod tạo **trực tiếp** (mutating admission chạy trước Kyverno validating webhook) — nên Pod trần thiếu resource sẽ **không** bị chặn, trong khi Deployment (100% cách production thật deploy) vẫn bị chặn đúng. Đây không phải lỗ hổng của policy, mà là chọn đúng fixture để demo phản ánh thực tế.

**Quét xác nhận không còn vi phạm thật trên toàn cluster** (trừ 2 exception đã đăng ký):

```sh
kubectl get clusterpolicy -o custom-columns='NAME:.metadata.name,ACTION:.spec.validationFailureAction,READY:.status.conditions[?(@.type=="Ready")].status'
# ca 4 policy: Enforce / True

# Kiểm tra request memory trên toàn bộ cluster

kubectl get pods -A -o json | jq -r '
  .items[] |
  select(.metadata.namespace != "kube-system") |
  .metadata.name as $pod | .metadata.namespace as $ns |
  .spec.containers[] |
  select(.resources.requests.memory == null or .resources.requests.cpu == null or .resources.limits.memory == null or .resources.limits.cpu == null) |
  "Pod: \($ns)/\($pod)\n  Container: \(.name)\n  req.cpu=\(.resources.requests.cpu // "<trống>")  req.mem=\(.resources.requests.memory // "<trống>")  lim.cpu=\(.resources.limits.cpu // "<trống>")  lim.mem=\(.resources.limits.memory // "<trống>")\n"
'

# Kiểm tra run as non root trên toàn bộ cluster

kubectl get pods -A -o json | jq -r '
  .items[] |
  select(.metadata.namespace != "kube-system") |
  .metadata.name as $pod |
  .metadata.namespace as $ns |
  .spec.securityContext.runAsNonRoot as $pod_runAsNonRoot |
  (.spec.containers[]?, .spec.initContainers[]?) |
  .securityContext.runAsNonRoot as $c_runAsNonRoot |
  .securityContext.allowPrivilegeEscalation as $allowPriv |
  select(
    ($allowPriv != false) or
    (($c_runAsNonRoot == null and $pod_runAsNonRoot != true) or $c_runAsNonRoot == false)
  ) |
  "Pod: \($ns)/\($pod)\n  Container: \(.name)\n  allowPrivilegeEscalation: \($allowPriv // "<trống>")\n  runAsNonRoot (Container): \($c_runAsNonRoot // "<trống>")\n  runAsNonRoot (Pod): \($pod_runAsNonRoot // "<trống>")\n"
'

# Kiểm tra latest tag có tồn tại trên container không trên toàn cluster 

kubectl get pods -A -o json | jq -r '
  .items[] | 
  select(.metadata.namespace != "kube-system") | 
  .metadata.name as $pod | .metadata.namespace as $ns |
  (.spec.containers[]?, .spec.initContainers[]?) |
  select(.image | endswith(":latest")) |
  "Pod: \($ns)/\($pod)\n  Container: \(.name)\n  Image: \(.image)\n"
'

```

## 6. Nghiệm thu

- Cả 4 lệnh demo bị từ chối đúng policy tương ứng, đúng thông điệp lỗi.
- Sau khi apply thật lên cluster (không phải dry-run), không có Pod nào ngoài `Running`/`Succeeded` toàn cluster.
- Argo CD: tất cả Application `Synced`/`Healthy`.
- Storefront: `200 OK` qua CloudFront — hardening không ảnh hưởng khách hàng.
- `flagd`: không đụng, vẫn `1/1` — không vi phạm luật chơi.

## 7. Sự cố quan sát được trong quá trình làm + xử lý (trung thực)

Mandate này có 3 sự cố thật, không chỉ là "làm xong luôn suôn sẻ" — ghi lại đầy đủ vì cùng tinh thần honesty như Mandate #3:

**(a) Kyverno "autogen" không tự sinh rule cho Deployment/StatefulSet/... ở policy baseline.**
Kyverno có cơ chế tự động nhân bản rule viết cho `Pod` sang các controller (Deployment, StatefulSet...), nhưng cơ chế này **không bao giờ cover `Rollout`** (CRD của Argo Rollouts) và đã âm thầm không sinh được cho `custom-baseline-security-context` (khả năng do JMESPath trộn lẫn cấp container/Pod trong `deny.conditions`). Hậu quả: apply thẳng 1 Deployment vi phạm baseline **không bị chặn ngay**, dù ReplicaSet nó tạo ra vẫn bị chặn 1 bước sau (không phải lỗ hổng bảo mật thật, nhưng là UX/timing gap thật). **Fix (PR #232):** khai tường minh cả 9 kind (`Pod, Deployment, StatefulSet, DaemonSet, Job, CronJob, ReplicaSet, ReplicationController, Rollout`) với JMESPath resolve đúng path cho từng loại, thay vì phụ thuộc autogen. Đã verify: `bad-root.yaml` (kind Deployment) giờ bị chặn **ngay ở bước apply Deployment**, không cần đợi ReplicaSet.

**(b) `argocd-application-controller` bị OOMKilled thật khi mở rộng resource hardening cho ArgoCD.**
Lúc thêm `limits.memory: 512Mi` cho StatefulSet này (bước chuẩn bị mục 3), lần đồng bộ đầu tiên của ArgoCD tự-quản-lý chính nó phải diff toàn bộ 59 resource + CRD `Application`/`AppProject` khá nặng → vượt 512Mi → `OOMKilled` (`exitCode: 137`), crash loop. **Fix:** nâng lên `1Gi`, verify ổn định (0 restart, dùng thật ~336Mi). Bài học ghi lại trong `kustomization.yaml` để không ai vô tình hạ lại xuống 512Mi.

**(c) Rule `require-run-as-non-root` thiếu fallback cấp Pod → chặn nhầm workload hợp lệ.**
Sau khi mở rộng toàn cluster, rule này chỉ đọc `securityContext.runAsNonRoot` ở **cấp container**, không có nhánh đọc lên cấp Pod. `argo-rollouts`, `argocd-redis`, `argocd-notifications-controller` chỉ khai `runAsNonRoot: true` ở cấp Pod (cách khai hợp lệ theo chuẩn Kubernetes — giá trị kế thừa xuống mọi container) → bị **chặn thật** mỗi lần các Deployment này cần đồng bộ lại. Xác nhận qua rule song song `require-effective-non-root` (đã có đủ fallback) vẫn PASS cho cùng 3 workload này — chứng minh đây là bug của rule, không phải vi phạm bảo mật thật. **Fix:** thêm 3 nhánh fallback (CronJob → Deployment/StatefulSet → Pod trần) đúng theo pattern đã dùng ở rule song song. Bằng chứng đầy đủ + lệnh verify: `docs/docx_cdo01/mandate-05-require-run-as-non-root-pod-fallback-fix.md`.

**Bài học chung:** khi Kyverno tự chặn tại admission, một rule viết thiếu fallback không chỉ "báo cáo sai" — nó **chặn thật** hoạt động vận hành bình thường (bao gồm cả GitOps tự đồng bộ). Trước khi Enforce bất kỳ rule mới nào đọc field cấp container, phải kiểm tra rule đó có đủ nhánh fallback lên cấp Pod/PodTemplate hay chưa.

## 8. Điểm mạnh của lần triển khai này

1. Cutover có kiểm soát: `Audit` → vá vi phạm thật → dọn exception thừa → `Enforce` từng policy, không "bật hết 1 lần".
2. Phạm vi thật sự toàn cluster (không chỉ `techx-tf3`) — kể cả hạ tầng vận hành (`argocd`, `argo-rollouts`) cũng phải tuân theo baseline, đúng tinh thần "không có vùng miễn trừ ngầm".
3. Exception được đăng ký công khai, có owner + review date — không phải im lặng loại trừ.
4. 3 sự cố thật trong lúc làm đều được root-cause chính xác (không đổ lỗi nhầm), fix đúng chỗ, và ghi lại làm bài học cho rule tương lai — kể cả khi ban đầu tự đánh giá quá nghiêm trọng (mục a) đã tự kiểm tra lại bằng test thật và sửa lại đánh giá.
5. Demo dùng đúng loại resource (`Deployment`, không phải Pod trần) để phản ánh đúng cách production thật deploy, thay vì chọn fixture "dễ pass demo".

## 9. Đề xuất sẽ làm sau Mandate #5

1. Dọn dứt điểm 2 exception còn lại trước review date 24/07: `aiops-engine` cần AIO02 tự thêm securityContext (hoặc chuyển vào GitOps tree); `kafka` cần đánh giá cơ chế ownership non-root (fsGroup/CSI) để bỏ hẳn root init.
2. Ký chính thức ADR 0010 (hiện "Accepted - mentor acceptance pending").
3. (Không gấp) PM-114 — Kyverno `verifyImages` Cosign tại admission-time, hiện Cosign mới verify off-cluster (mục 4.4 báo cáo nội bộ), chưa chặn tại admission.
4. Dọn ReplicaSet rác còn sót từ test cũ (`m5-t20`, `techx-tf3`, không owner, 0 pod thật) — không ảnh hưởng policy nhưng nên dọn cho sạch PolicyReport.

## 10. Cách mentor chạy lại / chứng kiến

**Cách A — Xem video** (link đầu file): toàn bộ 4 lệnh rejection-demo.

**Cách B — Tự chạy lại:**
```sh
export AWS_PROFILE=techx-new
# xác nhận 4 policy dang Enforce
kubectl get clusterpolicy -o custom-columns='NAME:.metadata.name,ACTION:.spec.validationFailureAction,READY:.status.conditions[?(@.type=="Ready")].status'
# chay lai dung 4 manifest vi pham
for f in docs/evidence/mandate-05/rejection-demo/*.yaml; do
  echo "=== $f ==="; kubectl apply --dry-run=server -f "$f"; echo
done
# thu apply lai 1 Deployment that dang chay san (hop le) de xac nhan khong bi chan oan
kubectl -n techx-tf3 get deploy cart -o yaml | kubectl apply --dry-run=server -f -
```
Quy trình + bằng chứng chi tiết hơn: `docs/docx_cdo01/mandate-05-gap-analysis-20260718.md`, `docs/docx_cdo01/mandate-05-cluster-wide-scope-expansion.md`, `docs/docx_cdo01/mandate-05-require-run-as-non-root-pod-fallback-fix.md`.

## 11. Đối chiếu Directive Mandate #5

| Yêu cầu | Trạng thái | Bằng chứng |
|---|---|---|
| *"Buộc `runAsNonRoot`, drop capability thừa"* | ✅ Đạt, toàn cluster | `custom-baseline-security-context` (8 rule) `Enforce`/`Ready`; mục 5, 7c |
| *"Cấm tag `latest`; pin digest hoặc tag cố định"* | ✅ Đạt, toàn cluster | `disallow-latest-tag` + `require-first-party-image-digest` `Enforce`/`Ready`; mục 5 |
| *"Mọi workload phải có resource request/limit"* | ✅ Đạt, toàn cluster | `require-resource-requests` `Enforce`/`Ready`; mục 3 (đã vá `argocd`/`kyverno`/`argo-rollouts` trước khi mở rộng) |
| *"Đẩy vào admission (policy-as-code), enforce có kiểm soát"* | ✅ Đạt | Audit→Enforce từng policy (18/07), mở rộng cluster-wide có pre-flight (19-20/07); mục 2, 3, 4 |

**Ràng buộc đã tuân thủ:** không đụng `flagd`/fault-injection; không mở route ops mới; exception có owner + review date thay vì im lặng bỏ qua; mọi thay đổi qua GitOps/PR (`#232`, `#256`-`#261`), không patch tay không ghi lại.

## 12. Kết luận

**PASS — 4 `ClusterPolicy` Enforce, phạm vi toàn cluster, admission chặn thật (không phải audit-only), đã demo bằng 4 manifest vi phạm thật.**

- 3 sự cố thật trong quá trình làm (autogen gap, ArgoCD OOMKill, rule thiếu fallback) đều đã root-cause và fix, ghi lại trung thực thay vì che giấu.
- 2 exception còn lại có kiểm soát, có hạn xử lý.
- Việc còn lại (không chặn PASS): ký ADR 0010, dọn 2 exception trước 24/07/2026.

## 13. Tài liệu liên quan

- ADR: `docs/adr/0010-mandate-05-runtime-hardening.md`
- Bằng chứng cutover 18/07: `docs/docx_cdo01/enforce-cutover-20260718.md`
- Đăng ký exception: `docs/evidence/mandate-05/exception-register.yaml`
- Phân tích mở rộng cluster-wide + trade-off ArgoCD resource: `docs/docx_cdo01/mandate-05-cluster-wide-scope-expansion.md`
- Điều tra gap ban đầu (autogen, PolicyReport pitfalls): `docs/docx_cdo01/mandate-05-gap-analysis-20260718.md`
- Bug fix `require-run-as-non-root`: `docs/docx_cdo01/mandate-05-require-run-as-non-root-pod-fallback-fix.md`
- Runbook resource ArgoCD: `docs/runbooks/argocd-resource-limits-kustomize-adoption.md`
- Báo cáo nội bộ đầy đủ (dành cho cả 2 team CDO, chi tiết per-service hơn): `docs/docx_cdo01/mandate-05-final-report.md`
