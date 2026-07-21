# Mandate 05 Native Migration — Progress Log

## Trạng thái tổng quan
- PM-168: code xong, dry-run sạch, **đã push + mở PR #291** (https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel/pull/291), nhánh `pm113-flagd-ui-kafka-digest-pin`. **Chưa merge.** Chờ merge + Argo sync để verify Warn/Audit thật.
- PM-169: đang làm — namespace `techx-tf3` đã chuyển label `audit/warn=restricted` (commit `bf83dd2`, chưa push), **CHƯA bật `enforce`**. Quyết định exception (không mơ hồ):
  - `kafka` (`m05-baseline-kafka-init-chown`): **không cần fix.** CDO02 xác nhận Mandate 8 (Kafka→MSK) đã xong, in-cluster Kafka không còn phục vụ traffic thật, chỉ chưa xoá. Bỏ qua fsGroup/non-root remediation — exception tự đóng khi workload bị dọn (theo dõi ở Mandate 8, không phải việc của task này).
  - `aiops-engine` (`m05-baseline-aiops-engine-runtime`): **chưa giải quyết được, để user tự xử lý sau.** AIO02 chưa đưa manifest để quản qua ArgoCD, CDO01 không có gì trong tay để sửa (deployment kubectl-apply tay ngoài GitOps). Không block phần còn lại của native migration.
  - → Do 2 exception trên vẫn còn tồn tại thật ở runtime (dù có lý do), **PSA `enforce=restricted` CHƯA được bật** — đúng gate DoD PM-169/PM-170 ("audit/warn trước, enforce chỉ sau khi có hướng rõ ràng"). Cân nhắc bật enforce sau khi kafka cũ bị xoá hẳn (Mandate 8 cleanup) dù aiops-engine vẫn còn treo — cần bàn lại với user lúc đó.
  - **⚠️ Cập nhật quan trọng (xem chi tiết ở nhật ký Task 5 bên dưới):** dry-run thử bật enforce phát hiện thêm **`otel-collector-agent`** (DaemonSet, chạy mọi node, hạ tầng quan sát dùng chung toàn cluster) cũng vi phạm PSA restricted (`hostPort` + `hostPath`) — **không nằm trong 2 exception đã đăng ký**, và rủi ro/phạm vi ảnh hưởng còn lớn hơn kafka/aiops-engine. Đây giờ là lý do chính khiến enforce chưa bật, không chỉ 2 exception cũ.
- PM-170: đang làm — **Task 4 + Task 6 xong**, Task 5 Step 1 (fixture `bad-root-pod.yaml`) xong, **enforce=restricted vẫn CHƯA bật** — xem phát hiện `otel-collector-agent` bên dưới, đây là lý do mới, quan trọng hơn cả 2 exception cũ. (evidence `docs/evidence/mandate-05/native-migration-20260721.md` + ADR 0010 update, commit `7366ffd`). **Task 5 (PSA enforce) chủ động treo**, không phải bỏ sót — chờ user quyết định thêm (kafka cũ bị xoá / aiops-engine có tiến triển). Task 4 chi tiết: (2 Binding VAP đổi `["Warn","Audit"]` → `["Deny"]`, commit `fd5b6f9`, dry-run sạch). **Quyết định của user (21/07):** gộp cả 6 task vào chung PR #291, không tách audit-bake riêng trên cluster sống trước khi Deny — khác 1 chút so với kỷ luật "audit trước, enforce sau, verify từng bước trên live cluster" đã dùng ở Mandate 5 gốc (Kyverno). Bù lại bằng: dry-run gate đầy đủ trước merge (5 fixture + không ảnh hưởng 18 workload thật) sẽ chạy ngay sau khi PR merge + Argo sync, trước khi coi Task 4 là "xong thật". Task 5 (PSA enforce) vẫn treo theo gate exception ở trên — **CHƯA làm**, không nằm trong quyết định gộp PR này (PSA enforce là quyết định riêng, rủi ro cao hơn VAP Deny vì có thể chặn nhầm Kafka/aiops-engine đang chạy thật).

## Nhật ký (mới nhất lên trên)

### 2026-07-21 — PM-170 Task 5: PHÁT HIỆN QUAN TRỌNG — `otel-collector-agent` cũng vỡ PSA restricted, chưa bật enforce

**Bối cảnh:** Task 5 Step 1 (tạo fixture `bad-root-pod.yaml`) đã xong, an toàn, đã commit (`e3d2aa9`). Trước khi bật `enforce=restricted` thật, user quyết định chấp nhận rủi ro đã biết (kafka/aiops-engine — xem PM-169) và yêu cầu bật thử bằng dry-run để xem hậu quả thật, không chỉ suy đoán.

**Kết quả dry-run** (`kubectl apply --dry-run=server` với `enforce=restricted` thêm vào namespace, `AWS_PROFILE=cdo_admin`):

```
Warning: existing pods in namespace "techx-tf3" violate the new PodSecurity enforce level "restricted:v1.35"
Warning: aiops-engine-5d5c7964c6-pz569: allowPrivilegeEscalation != false, unrestricted capabilities, runAsNonRoot != true, seccompProfile
Warning: kafka-7cdc4476fb-9fww2: allowPrivilegeEscalation != false, unrestricted capabilities, runAsNonRoot != true, runAsUser=0
Warning: otel-collector-agent-49sm6 (and 3 other pods): hostPort, restricted volume types
namespace/techx-tf3 configured (server dry run)
```

**Phát hiện mới, KHÔNG nằm trong 2 exception đã đăng ký (`docs/evidence/mandate-05/exception-register.yaml`):** DaemonSet **`otel-collector-agent`** — chạy trên **mọi node** (4 pod hiện tại = 4 node), là hạ tầng OpenTelemetry Collector dùng chung cho toàn bộ 18 service (mọi trace/metric đi qua đây trước khi tới Jaeger/Prometheus). Vi phạm cụ thể (đã đọc thẳng spec DaemonSet để xác nhận, không suy đoán):

- **6 container port khai `hostPort`** trên container `opentelemetry-collector`: `jaeger-compact` (UDP 6831), `jaeger-grpc` (14250), `jaeger-thrift` (14268), `otlp` (4317), `otlp-http` (4318), `zipkin` (9411). PSA `restricted` **cấm hoàn toàn `hostPort`** trên bất kỳ container nào.
- **1 volume `hostfs` dùng `hostPath`** — PSA `restricted` chỉ cho phép danh sách volume type an toàn (configMap, secret, emptyDir, projected, downwardAPI, persistentVolumeClaim, ephemeral...), không có `hostPath`.

**Vì sao đáng lo hơn kafka/aiops-engine:** kafka đang chết dần (Mandate 8 xong, sắp xoá) và aiops-engine chỉ là 1 workload đơn lẻ (dù đã có tiền sử CrashLoopBackOff) — còn `otel-collector-agent` là **DaemonSet dùng chung cho toàn cluster**, nếu bị kẹt admission ở bất kỳ node nào (Karpenter consolidation, node drain bảo trì, rolling update DaemonSet, node bị thay do Spot interruption...) thì **node đó mất hoàn toàn khả năng gửi trace/metric** — phạm vi ảnh hưởng rộng hơn nhiều, và tần suất pod DaemonSet bị tái tạo (theo mỗi lần node đổi) cao hơn hẳn 1 Deployment đơn lẻ.

**Quyết định (21/07, user xác nhận sau khi thấy dry-run thật):** **KHÔNG bật `enforce=restricted`** ở đợt này. Namespace giữ nguyên `audit/warn=restricted` (đã commit `bf83dd2`, không đổi gì thêm — bản dry-run có enforce chỉ để test, đã revert về đúng trạng thái đã commit, không tạo commit mới cho việc bật/tắt thử này).

**Việc cần làm trước khi bật enforce thật (chưa làm, để ngỏ cho member/user quyết định sau):**
1. `kafka`: chờ Mandate 8 dọn dẹp in-cluster Kafka (không phải việc của native migration này).
2. `aiops-engine`: chờ AIO02 đưa manifest vào GitOps + thêm securityContext chuẩn (user tự xử lý, đã ghi ở PM-169).
3. `otel-collector-agent`: **mới phát hiện, chưa có hướng xử lý nào được bàn.** 2 hướng khả dĩ (chưa đánh giá kỹ, chỉ liệt kê để tham khảo):
   - Đổi kiến trúc thu thập: bỏ `hostPort`, dùng Service (ClusterIP/headless) trỏ vào DaemonSet pod qua `hostNetwork: true` (một cơ chế native khác, nhưng cũng bị PSA `restricted` cấm — cần xem lại) hoặc đổi client (services gửi OTLP) trỏ thẳng qua Service DNS thay vì `localhost:<hostPort>` — ảnh hưởng tới cấu hình OTLP exporter của toàn bộ 18 service, không nhỏ.
   - Volume `hostfs` (`hostPath`) — cần hiểu rõ mục đích dùng để làm gì (có thể là log file node-level, hoặc container runtime socket) trước khi đề xuất thay thế.
   - Cả 2 hướng đều KHÔNG đơn giản như fsGroup cho kafka — cần điều tra kỹ hơn + có thể phải bàn với người đã dựng otel-collector ban đầu.
4. Chỉ sau khi cả 3 (hoặc user quyết định chấp nhận rủi ro cho 1/nhiều cái) mới nên bật `enforce=restricted`.

### 2026-07-21 — PM-170 Task 6: evidence + ADR 0010
- Tạo `docs/evidence/mandate-05/native-migration-20260721.md` — ghi rõ trạng thái thật (mới dry-run, PR chưa merge lúc viết), bảng target enforcement state, lý do PSA enforce chưa bật, danh sách lệnh verify còn nợ sau merge. Không claim "đã xong/đã live" ở đâu (đã tự kiểm `rg "PASS|completed|removed|retired"` — sạch, đúng ngữ cảnh).
- Cập nhật `docs/adr/0010-mandate-05-runtime-hardening.md` — thêm mục "Update 2026-07-21" nối tiếp (không xoá lịch sử Kyverno cũ), ghi đủ: VAP thay Kyverno cho image/resource, PSA restricted thay baseline security-context, lý do giữ Kyverno (Cosign+PolicyReport), kỷ luật cutover gộp 1 PR theo quyết định user, disposition 2 exception.
- Commit `7366ffd`.

### 2026-07-21 — PM-170 Task 4: VAP Warn/Audit → Deny
- User quyết định: gộp cả 6 task (PM-168+169+170 code phần) vào 1 PR #291 duy nhất, không tách PR audit-bake riêng, không cần kiểm tra PR đã merge chưa trước khi làm tiếp — làm liền Task 4.
- Sửa `gitops/policies/native/mandate-05-runtime-policy.yaml`: cả 2 `ValidatingAdmissionPolicyBinding` (`mandate05-native-resource-requirements-techx-tf3`, `mandate05-native-image-reference-techx-tf3`) đổi `validationActions` từ `["Warn","Audit"]` → `["Deny"]`. Commit `fd5b6f9`, dry-run sạch.
- Chưa push commit này + các commit PM-169/Task4 trước đó (`bf83dd2`, `2508015`, `fd5b6f9`) — đang ở local, chờ user tự push như lần trước.

### 2026-07-21 — PM-169 audit/warn=restricted staged
- Sửa `gitops/infrastructure/namespace-techx-tf3.yaml`: `audit`/`warn` từ `baseline` → `restricted` (+ version `v1.35`), **chưa thêm `enforce`**. Commit `bf83dd2`, dry-run sạch. Chưa push.
- Điều tra thật (agent Explore) trước khi quyết định hướng exception:
  - Kafka: init-container `init-kafka-data` (`values-prod.yaml`) chạy `mkdir -p /var/lib/kafka/data && chown -R 1000:1000 ...`, `runAsUser: 0`, trên Deployment `kafka` (không phải StatefulSet), PVC `kafka-data`. `podSecurityContext.fsGroup: 1000` **đã có sẵn** trong `values-prod.yaml` (thêm trước đó để né lỗi "Permission denied" lúc ghi EBS mới) — về lý thuyết đủ để bỏ chown-root, nhưng **không cần làm** vì user xác nhận CDO02 đã hoàn tất Mandate 8 (Kafka→MSK), Kafka in-cluster không còn dùng, sắp bị xoá.
  - aiops-engine: xác nhận **không có manifest nào trong repo này** — Deployment `aiops-engine` trong `techx-tf3` được `kubectl apply` tay ngoài GitOps bởi AIO02 (`last-applied-configuration` annotation, theo `mandate-05-final-report.md`). Không có gì để CDO01 tự sửa. User quyết định: để aiops-engine lại, tự xử lý sau, không chặn phần còn lại.
- Quyết định: giữ PSA ở `audit/warn=restricted`, **không bật `enforce`** cho tới khi có thêm quyết định của user (sau khi Kafka cũ bị dọn / AIO02 có tiến triển).

### 2026-07-21 13:36 — PM-168 push + PR
- User tự push nhánh `pm113-flagd-ui-kafka-digest-pin` (commit `818b139`, `7bc3290`) và mở PR #291:
  https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel/pull/291
- Jira PM-168: comment cập nhật link PR + checklist verify sẽ chạy sau khi merge.
- Bắt đầu chuyển sang bàn hướng xử lý exception `kafka`/`aiops-engine` cho PM-169 (xem execution guide mục 4 — 3 hướng đề xuất: fsGroup cho kafka, fix AIO02 cho aiops-engine, hoặc tách namespace).

### 2026-07-21 (phiên hiện tại, trước push)
- **Đã làm (PM-168, chưa commit):**
  - Tạo `gitops/apps/native-admission-policies-app.yaml` (Argo child Application, path `gitops/policies/native`, sync-wave 20, giống pattern `kyverno-policies-app.yaml`).
  - Tạo `gitops/policies/native/mandate-05-runtime-policy.yaml` — 2 `ValidatingAdmissionPolicy` (`mandate05-native-resource-requirements`, `mandate05-native-image-reference`) + 2 `ValidatingAdmissionPolicyBinding`, copy nguyên CEL đã review từ plan gốc Task 1, `matchConstraints.resourceRules` chỉ `resources: ["pods"]` đúng yêu cầu, `validationActions: ["Warn", "Audit"]`.
  - Sửa `gitops/infrastructure/limit-range.yaml`: xoá `default`/`defaultRequest`, chỉ còn `min: {cpu:5m, memory:8Mi}` / `max: {cpu:4, memory:4Gi}`.
  - Sửa `gitops/infrastructure/resource-quota.yaml`: thêm `requests.cpu: "12"`, `limits.cpu: "48"`, nâng `limits.memory` 24Gi→30Gi, giữ `requests.memory: 16Gi`. **Đã hỏi lại user về việc `requests.cpu=12` trùng đúng trần Karpenter NodePool `flash-sale-spot`** — user xác nhận dùng đúng 12 như plan gốc (Karpenter tự thêm node khi cần, không bị chặn cứng bởi trần NodePool này).
  - Tạo 5 file demo dưới `docs/evidence/mandate-05/native-rejection-demo/`: `good-native-compliant-pod.yaml`, `bad-latest-image-pod.yaml`, `bad-implicit-latest-pod.yaml`, `bad-first-party-tag-pod.yaml`, `bad-missing-resources-pod.yaml` (copy nguyên từ plan gốc Task 1 Step 3, digest fixture giả `sha256:801b...5f1d` chỉ dùng cho dry-run, không cần tồn tại thật trong ECR vì dry-run không pull image).
- **Verify đã chạy (dry-run, tunnel SSM, `AWS_PROFILE=cdo_admin`):**
  - `kubectl apply --dry-run=server` cho cả 4 file config mới/sửa — **sạch, không lỗi CEL compile, không lỗi schema**.
  - `kubectl apply --dry-run=server` cho 5 demo manifest — kết quả:
    - `bad-latest-image-pod.yaml`, `bad-implicit-latest-pod.yaml`, `bad-first-party-tag-pod.yaml` → bị chặn bởi **Kyverno** (`disallow-latest-tag`/`require-first-party-image-digest`, vẫn Enforce) — đúng dự kiến, không liên quan VAP mới (chưa tồn tại trên server).
    - `good-native-compliant-pod.yaml` → pass, đúng dự kiến.
    - `bad-missing-resources-pod.yaml` → **pass** dù thiếu hoàn toàn `resources` — **phát hiện thật, khớp đúng lý do PM-168 yêu cầu xoá LimitRange default**: LimitRange live hiện tại (chưa merge bản mới) tự điền `default`/`defaultRequest` trước khi Kyverno `require-resource-requests` kịp đánh giá, nên pod "trông hợp lệ" sau khi bị mutate. Đây không phải bug của VAP mới, là bằng chứng sống cho đúng gap đã ghi trong Mandate 5 gap-analysis cũ.
- **Chưa làm được / còn treo:**
  - Chưa verify hành vi Warn/Audit thật của 2 VAP mới — cần chúng tồn tại trên server thật, nghĩa là phải qua GitOps (merge PR → Argo CD sync `native-admission-policies`), không tự `kubectl apply` tay bỏ qua GitOps.
  - Chưa push/PR — sẽ hỏi user trước khi làm (theo đúng nguyên tắc không tự ý push).
- **Vướng mắc:** Không có.
- **Lưu ý phiên này:** dùng `AWS_PROFILE=cdo_admin` (không phải `techx-new` như ghi trong CLAUDE.md/handoff cũ) để access cluster qua tunnel SSM — user xác nhận profile này đã tạo sẵn, dùng cho phiên làm việc PM-166/167/168/169/170.
- **Commit:** `818b139` — "feat(pm-168): native VAP image-reference + resource-requirements (Warn/Audit)", nhánh `pm113-flagd-ui-kafka-digest-pin` (bằng đúng `origin/main` tại thời điểm branch, theo lựa chọn của user).

## Việc tiếp theo
1. Commit Task 1+3 (PM-168) trên nhánh hiện tại `pm113-flagd-ui-kafka-digest-pin` (bằng đầu `origin/main`, theo xác nhận của user).
2. Hỏi user trước khi push + mở PR.
3. Sau khi PR merge + Argo `native-admission-policies` Synced/Healthy: chạy lại 5 demo manifest, xác nhận 3 manifest ảnh/latest/digest xuất hiện trong Warn/Audit annotation của VAP mới (không chỉ bị Kyverno chặn), và audit log không có false-positive trên 18 workload hiện có — đúng DoD PM-168.
4. Bàn hướng xử lý exception kafka/aiops-engine (PM-169) trước khi code phần PSA.
