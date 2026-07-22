# Mandate #5 — Báo cáo Runtime Admission Hardening (chặn root / image trôi / thiếu resource ngay lúc admission)

**Directive:** Mandate 05 — Runtime Admission Hardening (xem `docs/adr/0010-mandate-05-runtime-hardening.md`)<br>
**Ngày Audit → Enforce cutover Kyverno (giai đoạn 1, đã lịch sử hoá):** 18-20/07/2026<br>
**Ngày chuyển sang cơ chế native (VAP + PSA) hoàn toàn, gỡ Kyverno (PM-172):** 21-22/07/2026<br>
**Nhóm thực hiện:** CDO01 (Security, chủ trì) phối hợp CDO02 (Karpenter elastic capacity, resource headroom) và AIO02 (theo dõi `aiops-engine`)<br>
**Người xác nhận/chứng kiến (mentor):** _(điền)_<br>
**Video demo (native, 22/07):** _(điền link — quay lại theo bộ lệnh mục 4)_<br>
**Kết quả:** **PASS — enforcement thật tại admission hoàn toàn bằng cơ chế native Kubernetes (`ValidatingAdmissionPolicy` + Pod Security Admission), không còn phụ thuộc công cụ ngoài (Kyverno đã gỡ hẳn).**

> **Vì sao báo cáo này được viết lại:** bản gốc (18-20/07) dùng Kyverno làm cơ chế chặn chính, bị mentor đánh **FAIL** vì Kyverno là công cụ third-party, không phải "native" theo đúng yêu cầu directive. Báo cáo này thay thế hoàn toàn phần kỹ thuật bằng kiến trúc mới: `ValidatingAdmissionPolicy` (VAP, built-in Kubernetes từ 1.30) cho image/resource, `Pod Security Admission` (PSA, built-in từ lâu hơn) cho root/privileged. Lịch sử Kyverno vẫn giữ lại trong mục 7-8 vì đó là quá trình thật đã xảy ra, không xoá để giữ tính trung thực.

---

## 1. Mục tiêu & phạm vi

**Chứng minh:** mọi workload trong cluster — không chỉ lúc code review — bị **chặn ngay tại API server** nếu:
1. container chạy bằng root,
2. image dùng tag `latest`/trôi (không pin digest cho image nội bộ),
3. thiếu khai báo `requests`/`limits` CPU-memory.

Và việc chặn này là **policy-as-code tại admission**, dùng **đúng cơ chế Kubernetes gốc**, không cài thêm controller/CRD/webhook của bên thứ ba nào.

**Phạm vi:**
- **First-party**: 18 workload ứng dụng của `techx-tf3` (chart chính TechX Corp).
- **Toàn namespace `techx-tf3`** — `enforce=restricted` (PSA) áp cho mọi pod trong namespace, VAP áp qua `namespaceSelector`.
- **1 exception còn mở** (`aiops-engine`), đăng ký công khai trong `docs/evidence/mandate-05/exception-register.yaml` (chi tiết mục 6).

## 2. Cơ sở kỹ thuật (đã build, verify sống trước demo)

| Lớp | Cơ chế | Trạng thái | Bằng chứng |
|---|---|---|---|
| Image reference (no-`latest`, first-party digest) | `ValidatingAdmissionPolicy` `mandate05-native-image-reference` + `ValidatingAdmissionPolicyBinding` | **`Deny`** | `gitops/policies/native/mandate-05-runtime-policy.yaml` |
| Resource requests/limits bắt buộc | `ValidatingAdmissionPolicy` `mandate05-native-resource-requirements` + `ValidatingAdmissionPolicyBinding` | **`Deny`** | cùng file trên; `LimitRange` cũ (từng tự điền default che giấu vi phạm) đã bị xoá hẳn khỏi `techx-tf3` |
| Root / privileged / capability / seccomp | **Pod Security Admission** mức `restricted` | **`enforce`** (namespace label) | `gitops/infrastructure/namespace-techx-tf3.yaml` |
| Kyverno (từng là cơ chế chính giai đoạn 18-20/07) | 4 `ClusterPolicy` | **Đã gỡ hẳn** (PM-172, 22/07) — xem mục 8 | N/A, lịch sử ở mục 7 |

**Vì sao chọn VAP+PSA thay vì tiếp tục Kyverno:** cả hai đều là API built-in của Kubernetes (VAP GA từ 1.30, cluster đang chạy 1.35; PSA là admission plugin gốc từ lâu hơn) — không cần cài thêm gì vào cluster, đúng yêu cầu "native" của mentor. Kyverno vẫn là lựa chọn hợp lý về mặt kỹ thuật (CNCF graduated), nhưng không thoả điều kiện "native" đúng nghĩa mentor chấm.

## 3. Lộ trình cutover (2 giai đoạn, có kiểm soát ở cả 2)

### Giai đoạn 1 — Kyverno Audit → Enforce (18-20/07, lịch sử)
Xem chi tiết đầy đủ ở mục 7-8 (giữ lại nguyên trạng làm lịch sử). Tóm tắt: 4 `ClusterPolicy` cutover từng cái một, mở rộng cluster-wide, PR #232/#256-#261.

### Giai đoạn 2 — Native VAP+PSA thay thế hoàn toàn, gỡ Kyverno (21-22/07)
1. **21/07** — Viết `ValidatingAdmissionPolicy`+`Binding` cho image/resource, `Warn/Audit` trước (PM-168, PR #291), verify dry-run sạch, merge.
2. **21/07** — PSA namespace label `audit/warn=restricted` trước (PM-169, PR #291), chưa `enforce`. Phát hiện + xử lý 2 exception cũ (kafka: theo dõi Mandate 8; aiops-engine: để AIO02).
3. **21/07** — VAP `Warn/Audit → Deny` (PM-170, PR #291, gộp theo quyết định user — 1 PR thay vì tách nhiều PR nhỏ, bù bằng dry-run gate đầy đủ trước merge).
4. **21/07, phát hiện quan trọng** — dry-run thử bật PSA `enforce` phát hiện thêm 1 blocker chưa biết trước: DaemonSet `otel-collector-agent` (dùng `hostPort`+`hostPath`, vi phạm `restricted`) — **không nằm trong 2 exception cũ**, chặn `enforce` lại.
5. **21-22/07** — Xử lý OTEL: `otel-gateway` (Deployment, PSA-safe) nhận hết app telemetry (PR #300/#301); `otel-node-agent` (DaemonSet mới, PSA-safe, namespace `observability-system` riêng) thay thế phần host/kubelet/cluster metric của agent cũ (PR #302/#303/#310/#332, gồm 1 sự cố Pending do CPU headroom giữa chừng — xem mục 8); bổ sung `k8s_cluster` receiver + `receiver_creator`/`k8s_observer` cho đủ parity (PR #335/#336); chuyển self-telemetry của `jaeger` sang `otel-gateway` (PR #336).
6. **22/07** — Verify sống bằng Prometheus: `otel-collector-agent` về **0 span/metric thật** (loại self-telemetry) trong 2 phút liên tiếp; `otel-node-agent` cho đủ metric host/kubelet/cluster tươi (2-11 giây tuổi). Tắt hẳn `otel-collector-agent` (PR #337).
7. **22/07** — Xác nhận độc lập Kafka legacy đã xoá thật (PR #324, `git log` verify, không chỉ tin báo cáo). Bỏ qua xử lý `aiops-engine` theo quyết định — chấp nhận rủi ro (đã ghi rõ ràng, xem mục 6).
8. **22/07** — Bật PSA `enforce=restricted` thật (PR #338). Dry-run trước khi merge chỉ còn đúng 1 cảnh báo (`aiops-engine`) — đúng dự kiến.
9. **22/07** — Gỡ Kyverno (PM-172, đã bật đèn xanh): Audit (PR #339) → gỡ 4 `ClusterPolicy`+app (PR #340) → gỡ controller (PR #341).

## 4. Quy trình demo mentor (native, 22/07 — dùng bộ lệnh này để quay video)

```bash
export AWS_PROFILE=cdo_admin
cd /Users/tan/Desktop/phase3/Phase3-TF3-Infra-Sentinel

echo "=== 0. Xác nhận PSA enforce + VAP Deny đang live ==="
kubectl get ns techx-tf3 -o jsonpath='{.metadata.labels}'; echo
kubectl get validatingadmissionpolicybinding -o custom-columns='NAME:.metadata.name,ACTION:.spec.validationActions'

for f in docs/evidence/mandate-05/native-rejection-demo/*.yaml; do
  echo "=== $f ==="
  kubectl apply --dry-run=server -f "$f"
  echo
done
```

| File | Vi phạm cố ý | Cơ chế chặn |
|---|---|---|
| `good-native-compliant-pod.yaml` | *(không có, phải qua)* | — |
| `bad-latest-image-pod.yaml` | Image dùng tag `:latest` | **VAP** `mandate05-native-image-reference` |
| `bad-implicit-latest-pod.yaml` | Image không ghi tag (latest ngầm định) | **VAP** `mandate05-native-image-reference` |
| `bad-first-party-tag-pod.yaml` | Image ECR nội bộ dùng tag thay vì `@sha256:` digest | **VAP** `mandate05-native-image-reference` |
| `bad-missing-resources-pod.yaml` | Container không khai `requests`/`limits` | **VAP** `mandate05-native-resource-requirements` |
| `bad-root-pod.yaml` | Container không set `runAsNonRoot`, `runAsUser:0`, `allowPrivilegeEscalation:true` | **PSA** `restricted:v1.35` |

## 5. Kết quả (verify sống 22/07, trước khi ghi vào báo cáo)

```
# 5 fixture đầu — VAP native denied
The pods "..." is invalid: : ValidatingAdmissionPolicy 'mandate05-native-image-reference' with binding
  'mandate05-native-image-reference-techx-tf3' denied request: Images must use an explicit non-latest
  tag or immutable sha256 digest.
The pods "..." is invalid: : ValidatingAdmissionPolicy 'mandate05-native-resource-requirements' with
  binding 'mandate05-native-resource-requirements-techx-tf3' denied request: All containers and
  initContainers must explicitly define requests.cpu, requests.memory, limits.cpu, and limits.memory.

# fixture cuối — PSA native denied (khác định dạng lỗi, khác cơ chế)
Error from server (Forbidden): error when creating "...bad-root-pod.yaml": pods "mandate05-native-bad-root"
  is forbidden: violates PodSecurity "restricted:v1.35": allowPrivilegeEscalation != false (container "app"
  must set securityContext.allowPrivilegeEscalation=false), unrestricted capabilities (container "app" must
  set securityContext.capabilities.drop=["ALL"]), runAsNonRoot != true (pod or container "app" must set
  securityContext.runAsNonRoot=true), runAsUser=0 (container "app" must not set runAsUser=0), seccompProfile
  (pod or container "app" must set securityContext.seccompProfile.type to "RuntimeDefault" or "Localhost")
```

**Điểm mấu chốt để nhấn mạnh với mentor:** lệnh cuối trả về `Error from server (Forbidden)` — khác định dạng với 5 lệnh đầu (`The pods "..." is invalid: ValidatingAdmissionPolicy ... denied`). Đây là **2 cơ chế admission built-in khác nhau của Kubernetes** (`PodSecurity` admission plugin + `ValidatingAdmissionPolicy` API) cùng hoạt động, không có Kyverno hay bất kỳ webhook bên thứ 3 nào tham gia.

**Quét xác nhận không còn vi phạm thật trên toàn cluster** (trừ 1 exception đã đăng ký):
```sh
kubectl apply --dry-run=server -f gitops/infrastructure/namespace-techx-tf3.yaml
# Warning: existing pods in namespace "techx-tf3" violate the new PodSecurity enforce level "restricted:v1.35"
# Warning: aiops-engine-...: allowPrivilegeEscalation != false, unrestricted capabilities, runAsNonRoot != true, seccompProfile
# → CHỈ đúng 1 dòng cảnh báo, đúng 1 pod (aiops-engine đã đăng ký exception)
```

## 6. Nghiệm thu

- Cả 6 lệnh demo cho đúng kết quả kỳ vọng — 5 bị VAP chặn, 1 bị PSA chặn, không cái nào lọt qua sai.
- Argo CD: tất cả Application `Synced/Healthy` xuyên suốt quá trình cutover (verify nhiều lần trong 22/07, không chỉ 1 lần chụp).
- Storefront + `/api/products`: `200 OK` trước/trong/sau toàn bộ quá trình — không downtime.
- `flagd`: không đụng, vẫn hoạt động — không vi phạm luật chơi.
- `aiops-engine`: pod đang chạy **không bị dừng** (PSA chỉ đánh giá lúc admission, không hồi tố) — nhưng lần tái tạo tiếp theo sẽ bị chặn thật cho tới khi AIO02 hardening. Đây là **exception còn mở duy nhất**, đã đăng ký công khai (`docs/evidence/mandate-05/exception-register.yaml`), owner AIO02, review date 24/07.

## 7. Sự cố quan sát được — giai đoạn Kyverno (18-20/07, lịch sử, giữ nguyên để trung thực)

**(a) Kyverno "autogen" không tự sinh rule cho Deployment/StatefulSet/... ở policy baseline.**
Kyverno có cơ chế tự động nhân bản rule viết cho `Pod` sang các controller, nhưng không cover `Rollout` (CRD Argo Rollouts). Fix bằng cách khai tường minh 9 kind (PR #232).

**(b) `argocd-application-controller` bị OOMKilled thật khi mở rộng resource hardening cho ArgoCD.**
`limits.memory: 512Mi` không đủ cho lần đồng bộ đầu tiên diff 59 resource + CRD lớn. Nâng lên `1Gi`.

**(c) Rule `require-run-as-non-root` thiếu fallback đọc `runAsNonRoot` cấp Pod → chặn nhầm workload hợp lệ.**
`argo-rollouts`/`argocd-redis`/`argocd-notifications-controller` chỉ khai ở cấp Pod, bị chặn thật cho tới khi vá.

## 8. Sự cố quan sát được — giai đoạn native VAP+PSA (21-22/07)

**(d) LimitRange vẫn tự điền default dù chỉ còn `min`/`max` (không còn `default`/`defaultRequest`).**
Kubernetes `LimitRanger` admission plugin vẫn materialize `default`/`defaultRequest` từ `max` khi chỉ khai `min`/`max` — khiến `bad-missing-resources-pod.yaml` vẫn lọt qua sau khi merge PR VAP đầu tiên. Fix: xoá hẳn `LimitRange` khỏi GitOps, chỉ giữ VAP + `ResourceQuota`.

**(e) Argo Application `techx-corp`/`techx-corp-bootstrap` bị patch tay ngoài GitOps, mất `automated` syncPolicy suốt ~6 tiếng.**
Một thành viên team tắt tay auto-sync để xử lý riêng vấn đề `hostPort` OTEL, khiến 15 commit tồn đọng không lên cluster — bao gồm cả phần `otel-node-agent` (PR #302/#303) tưởng đã merge nhưng chưa từng chạy thật. Phát hiện qua đối chiếu `sync.revision` live với `git log`, không tin theo báo cáo tự khai. Khôi phục bằng cách patch lại đúng `syncPolicy.automated` theo git, gây 1 lần "big bang" sync 15 commit cùng lúc.

**(f) `otel-node-agent` mới bật chỉ phủ 4/7 node do thiếu `tolerations` cho taint Karpenter elastic + node stateful.**
Fix bằng cách thêm 2 `tolerations` (PR #333), verify lại đủ 7/7 node.

**(g) `otel-node-agent` thiếu 2 receiver so với agent cũ: `k8s_cluster` (metric cluster-wide) và `receiver_creator`/`k8s_observer` (annotation-discovery).**
Phát hiện qua so sánh config `helm template` thật giữa 2 DaemonSet (không chỉ đọc preset flag). Fix bằng cách bật đúng 2 preset có sẵn của chart (PR #335/#336) — không viết tay OTel config. RBAC (`ClusterRole`) cũng phải đổi `create: false → true` để chart tự sinh đủ quyền `Lease` (leader election) + cluster resource read.

**(h) Karpenter elastic Batch 1 (`currency`/`quote`/`shipping`) lần đầu thất bại — 2 replica bị dồn chung 1 node.**
`topologySpreadConstraints` chỉ có `whenUnsatisfiable: ScheduleAnyway` (mềm) trên hostname, không có `minDomains`, không ràng buộc zone. Fix: chuyển cả 2 key (hostname + zone) sang `DoNotSchedule` (cứng) + `minDomains: 2`. Áp dụng lại đúng pattern này cho Batch 2 (`payment`/`cart`/`product-catalog`/`product-reviews`) và Batch 3 (`frontend`/`frontend-proxy`/`checkout`/`otel-gateway`) — verify 11/11 service đều đúng 2 node khác nhau, không co-locate.

**Bài học chung (áp dụng cả 2 giai đoạn):** không tin theo self-report/preset-flag/trạng thái Jira — luôn verify bằng lệnh thật trên cluster sống (`kubectl`, Prometheus, `git log`) trước khi kết luận hoặc merge bước tiếp theo.

## 9. Điểm mạnh của lần triển khai native này

1. Đúng yêu cầu "native" của mentor — không còn phụ thuộc công cụ bên thứ 3 nào cho admission enforcement.
2. Cutover có kiểm soát ở cả 2 lớp (VAP: Warn/Audit→Deny; PSA: audit/warn→enforce), mỗi bước đều dry-run + verify sống trước khi merge.
3. Phát hiện + xử lý dứt điểm 1 blocker hoàn toàn mới phát sinh giữa chừng (`otel-collector-agent`) mà không có trong kế hoạch ban đầu — chứng minh bằng Prometheus thật (0 span/metric, không phải suy đoán) trước khi cutover.
4. Không tin lời tự báo cáo ở bất kỳ bước nào — verify độc lập Kafka đã xoá (git log), verify độc lập node-agent đủ parity (so sánh config `helm template` thật), verify độc lập Argo drift (đối chiếu revision).
5. Gỡ Kyverno (PM-172) chỉ thực hiện sau khi cả 2 cơ chế thay thế đã chứng minh đầy đủ bằng chứng live — không gỡ vội.

## 10. Đề xuất sau Mandate #5

1. `aiops-engine` — exception còn mở duy nhất, cần AIO02 hardening hoặc tách namespace trước 24/07.
2. Ký chính thức ADR 0010 (mentor countersignature).
3. **Cosign `verifyImages`** (PM-114/127/128) — mất đi cùng Kyverno, chưa có giải pháp native/thay thế. Cosign verify hiện vẫn chạy off-cluster (CI), chưa chặn tại admission-time. Cần thiết kế lại (có thể bằng 1 admission webhook nhẹ tự viết, hoặc tool native khác) nếu vẫn cần chặn tại admission.
4. PolicyReport background reconciliation (quét resource đã tồn tại, không chỉ admission-time) — cũng mất theo Kyverno, VAP/PSA không làm được việc này. Cân nhắc có cần thay thế hay chấp nhận admission-time-only là đủ.
5. Xoá `opentelemetry-collector` (agent cũ) khỏi chart hẳn — hiện mới tắt (`enabled: false`), giữ code lại phòng rollback nhanh, sẽ dọn ở đợt cleanup cuối.

## 11. Cách mentor chạy lại / chứng kiến

```sh
export AWS_PROFILE=cdo_admin
# xác nhận VAP Deny + PSA enforce đang live
kubectl get validatingadmissionpolicybinding -o custom-columns='NAME:.metadata.name,ACTION:.spec.validationActions'
kubectl get ns techx-tf3 -o jsonpath='{.metadata.labels}'; echo
# xác nhận Kyverno đã gỡ hẳn (không còn CRD/controller)
kubectl get clusterpolicy 2>&1   # phải báo "the server doesn't have a resource type" hoặc rỗng
kubectl get pods -n kyverno 2>&1  # phải rỗng / namespace không tồn tại

# chạy lại đúng 6 manifest demo
for f in docs/evidence/mandate-05/native-rejection-demo/*.yaml; do
  echo "=== $f ==="; kubectl apply --dry-run=server -f "$f"; echo
done

# thử apply lại 1 Deployment thật đang chạy sẵn (hợp lệ) để xác nhận không bị chặn oan
kubectl -n techx-tf3 get deploy cart -o yaml | kubectl apply --dry-run=server -f -
```
Quy trình + bằng chứng chi tiết hơn: `docs/docx_cdo01/mandate05/karpenter-elastic-batch2-batch3-20260722.md`, `docs/docx_cdo01/mandate05/mandate-05-handoff-20260722-review.md`, `docs/docx_cdo01/mandate05/mandate-05-vap-migration-gap-analysis.md`.

## 12. Đối chiếu Directive Mandate #5

| Yêu cầu | Trạng thái | Bằng chứng |
|---|---|---|
| *"Buộc `runAsNonRoot`, drop capability thừa"* | ✅ Đạt, native (PSA `restricted`) | Mục 4-6 |
| *"Cấm tag `latest`; pin digest hoặc tag cố định"* | ✅ Đạt, native (VAP `mandate05-native-image-reference`) | Mục 4-6 |
| *"Mọi workload phải có resource request/limit"* | ✅ Đạt, native (VAP `mandate05-native-resource-requirements`) | Mục 4-6 |
| *"Đẩy vào admission (policy-as-code), enforce có kiểm soát"* | ✅ Đạt, và **native hoàn toàn** (không còn công cụ ngoài) | Mục 3 |

**Ràng buộc đã tuân thủ:** không đụng `flagd`/fault-injection; không mở route ops mới; exception còn lại có owner + review date; mọi thay đổi qua GitOps/PR, không patch tay không ghi lại (kể cả sự cố Argo drift ở mục 8(e), đã xử lý lại đúng qua GitOps, không lặp lại vi phạm).

## 13. Kết luận

**PASS — enforcement thật tại admission, hoàn toàn bằng cơ chế native Kubernetes (`ValidatingAdmissionPolicy` + `Pod Security Admission`), Kyverno đã gỡ hẳn khỏi cluster (PM-172).**

- Đã xử lý dứt điểm đúng lý do mentor đánh FAIL bản báo cáo trước (dùng công cụ non-native).
- 8 sự cố thật xuyên suốt cả 2 giai đoạn đều đã root-cause và fix, ghi lại trung thực.
- 1 exception còn mở (`aiops-engine`), có kiểm soát, có hạn xử lý, không chặn PASS.
- Việc còn lại (không chặn PASS): ký ADR 0010, thiết kế thay thế cho Cosign `verifyImages`/PolicyReport nếu vẫn cần, dọn code `opentelemetry-collector` cũ khỏi chart.

## 14. Tài liệu liên quan

- ADR: `docs/adr/0010-mandate-05-runtime-hardening.md` (mục "Update 2026-07-22" — quyết định + rollback đầy đủ nhất)
- Exception register: `docs/evidence/mandate-05/exception-register.yaml` (schemaVersion 2, cập nhật 22/07)
- Gap analysis CEL/VAP ban đầu (PM-167): `docs/docx_cdo01/mandate05/mandate-05-vap-migration-gap-analysis.md`
- Bàn giao + đối chiếu 22/07 (member): `docs/docx_cdo01/mandate05/mandate-05-handoff-20260722-review.md`
- Karpenter elastic Batch 2/3 + toàn bộ quá trình OTEL parity + bộ lệnh demo: `docs/docx_cdo01/mandate05/karpenter-elastic-batch2-batch3-20260722.md`
- Progress log PM-168/169/170: `docs/docx_cdo01/mandate-05-native-migration-progress.md`
- Lịch sử Kyverno Enforce cutover (giai đoạn 1, 18-20/07): `docs/docx_cdo01/enforce-cutover-20260718.md`, `docs/docx_cdo01/mandate-05-cluster-wide-scope-expansion.md`, `docs/docx_cdo01/mandate-05-gap-analysis-20260718.md`, `docs/docx_cdo01/mandate-05-require-run-as-non-root-pod-fallback-fix.md`
- Báo cáo nội bộ đầy đủ (2 team CDO, per-service): `docs/docx_cdo01/mandate-05-final-report.md` _(cần cập nhật riêng nếu vẫn dùng)_
