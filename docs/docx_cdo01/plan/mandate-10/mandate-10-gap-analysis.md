# PM-124 — Mandate 10 CI/CD Supply-Chain Gap Analysis

**Loại tài liệu:** audit và source of truth cho planning; không phải bằng chứng đã đóng mandate.
**Quy tắc verdict:** chỉ ghi `Implemented`, `PASS` hoặc `Done` khi có evidence được liên kết. Thiếu evidence phải ghi `Gap`, `Blocked` hoặc `Needs reconciliation`.

## 1. Evidence boundary

PR metadata chỉ chứng minh một PR đã có review/check tại một thời điểm; không thay thế export Branches/Rulesets. Artifact release (`approved-images.json`, báo cáo Cosign/Trivy) được sinh lúc runtime trong GitHub Actions, không phải file tĩnh trong workspace. Truy ngược phải xác định run, tải artifact bằng `gh run download`, kiểm run ID/attempt và kiểm retention.

## 2. Sáu yêu cầu và verdict hiện tại

### Yêu cầu 1: 🟡 Đạt một phần — cần evidence admin

**Đã chứng minh:** PR cần ít nhất một approval; có ít nhất một check từng tham gia chặn merge.

**Chưa chứng minh:** exact required-status-check contexts; Build/Trivy/Gitleaks/IaC/SAST có thực sự required; và check skipped/cancel có khóa merge không.

**Evidence cần:** screenshot/export `Settings → Branches/Rulesets`, tên exact mọi required check, và một PR test đỏ cho thấy merge bị khóa. Không suy luận từ PR #273 hoặc API 404 của token non-admin.

### Yêu cầu 2: 🟡 Gate scan hiện có nhưng PR protection chưa đủ

| Gate | Chạy trên PR? | Có thể chặn merge? | Verdict |
|---|---:|---:|---|
| Gitleaks | Có | Có nếu required | Có workflow, cần xác nhận protection |
| Trivy image | Không | Không | Chỉ chặn release sau merge; gap PR-mode |
| IaC scan | Không | Không | Chưa triển khai |
| SAST | Không | Không | Chưa triển khai |

`build-push-ecr.yml` chỉ chạy `workflow_dispatch` và push `main`; Trivy image gate hiện không thể là PR gate. PM-125 phải thêm PR-mode image build + Trivy scan, cùng IaC và SAST.

### Yêu cầu 3: 🟡 Immutable release có nền tảng; SBOM/admission cần reconcile

Cosign keyless và digest release có trong pipeline, nhưng Jira đang mâu thuẫn: PM-127 `To Do` có SBOM + verifyImages, còn PM-128 `Done` nói verifyImages đóng PM-114.

Không kết luận PM-114 còn `To Do`. Cần xác minh PR/commit PM-128, policy Git, `kubectl get clusterpolicy`, trạng thái `Enforce`/`Ready=True`, signed image pass, và unsigned/wrong-identity image bị đúng signature policy reject. Thiếu evidence phải reopen/correct PM-128.

### Yêu cầu 4: ❌ Pinning chưa đạt; audit cuối phải động

- Audit cũ ghi 6 workflow; audit hiện tại thấy 7 workflow: `build-push-ecr`, `scan-external-images`, `secret-scan`, `terraform-plan`, `terraform-apply`, `validate-production-access`, `test-image-bump`.
- `7` chỉ là snapshot hiện tại, không phải DoD hard-code. Final checker phải quét toàn bộ `.github/workflows/*.{yml,yaml}` tại final-main SHA.
- Examples cũ `checkout@v3`/`docker/login-action@v2` không đại diện repo hiện tại; refs đang có gồm `checkout@v6`, `setup-terraform@v3`, `gitleaks-action@v3`.
- DoD: `0 external uses:` trong mọi workflow final còn tag, branch hoặc short SHA; mọi action phải full 40-char SHA và comment version gốc.

### Yêu cầu 5: 🟡 Provenance data tồn tại runtime, chưa là chain đóng

`approved-images.json`, Trivy/Cosign evidence là workflow artifact. Trace phải dùng aggregate artifact đúng run attempt; approved manifest có retention ngắn hơn Trivy/Cosign trong thiết kế hiện tại, nên cần nâng retention hoặc durable archive. PM-129/130 phải cung cấp trace digest → source SHA → PR approval → scan → signature/Rekor → SBOM.

### Yêu cầu 6: ✅ Implemented / 🟡 Evidence cần liên kết

Workflow có `prepare` và `git diff` cho scoped build, nhưng chưa có run thật để gọi là đạt hoàn toàn. Evidence bắt buộc: PR chỉ sửa một service; prepare chọn đúng service; matrix chỉ build service đó; service không đổi bị skip; aggregate manifest khớp scoped set; image-bump chỉ đổi digest service đó; link run PM-131.

## 3. Jira mapping và reconciliation

| Requirement | Implementation task | Evidence/final task |
|---|---|---|
| Required merge gate | PM-125 | PM-132 |
| IaC/Secret/SAST/Trivy PR gate | PM-126 + PM-125 | PM-132 |
| SBOM + signature admission | PM-127/PM-128 | PM-132 |
| Action SHA + Docker digest | PM-129 | PM-132 |
| Full provenance | PM-129/PM-130 | PM-132 |
| Scoped build/deploy | PM-131 | PM-132 |

| Jira | Jira status | Code/evidence status | Required action |
|---|---|---|---|
| PM-126 | Done | IaC/SAST chưa thấy evidence final-main | Reopen hoặc link PR chưa merge |
| PM-128 | Done | verifyImages chưa có evidence đủ | Reconcile/reopen nếu cần |
| PM-130 | Done | Script còn nằm scope PM-129 | Chốt owner/source of truth |
| PM-131 | Done | Chưa có linked scoped-build run | Bổ sung run evidence |

## 4. Priority fixes before review

1. PM-125: một `Secure delivery gate` luôn chạy; aggregate Gitleaks, PR Trivy, conditional IaC/SAST và `if: always()`. Branch protection chỉ require check aggregate.
2. PM-127: đổi tên/spec khỏi PM-114; reconcile PM-127/128 bằng live/Git evidence.
3. PM-129: discovery dynamic mọi workflow tại final main, không audit `0/7`.
4. PM-132: dùng contract provenance flags; manifest unsigned compliant các policy khác và dùng ECR digest thật; không pre-fill `ĐẠT`.
5. Rebase branch lên latest `main`, chạy lại audit/checks, đổi title/body PR và request review chỉ sau evidence đủ.
