# Mandate 05 Native Migration — Progress Log

## Trạng thái tổng quan
- PM-168: đang làm — code xong, dry-run sạch, **đã push + mở PR #291** (https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel/pull/291), nhánh `pm113-flagd-ui-kafka-digest-pin`. Chờ merge + Argo sync để verify Warn/Audit thật.
- PM-169: chưa bắt đầu — bị block bởi 2 exception kafka/aiops-engine (xem execution guide mục 4), cần bàn hướng trước khi code.
- PM-170: chưa bắt đầu — phụ thuộc PM-168 + PM-169 xong trước.

## Nhật ký (mới nhất lên trên)

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
