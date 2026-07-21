# PM-124 — Mandate 10 CI/CD Supply-Chain Gap Analysis

**Loại tài liệu:** audit và source of truth cho planning; không phải bằng chứng đã đóng mandate.
**Quy tắc verdict:** chỉ ghi `Implemented`, `PASS` hoặc `Done` khi có evidence được liên kết. Thiếu evidence phải ghi `Gap`, `Blocked` hoặc `Needs reconciliation`.

## 0. Canonical source, baseline và hygiene gate

- Canonical gap analysis duy nhất là file này: `docs/docx_cdo01/plan/mandate-10/mandate-10-gap-analysis.md`.
- Không tạo hoặc giữ bản sao tại `docs/docx_cdo01/mandate-10-gap-analysis.md`. Tài liệu khác chỉ được link về canonical path, không được copy verdict sang một source of truth thứ hai.
- Snapshot review này được đối chiếu tại `main@bbe25038b47bf743b5e35ec6f997d89380f639fd` ngày `2026-07-21`. Mọi final verdict phải chạy lại trên exact final-main SHA; không mặc định snapshot này vẫn hiện hành.
- Trước merge, toàn bộ Markdown trong thư mục Mandate 10 phải trả về zero match cho Unicode format controls (`Cf`), bao gồm bidi override/isolate và BOM ẩn giữa file. Unicode tiếng Việt bình thường được giữ nguyên.

Machine-generated audit bundle bắt buộc:

```text
docs/evidence/mandate-10/audit/
├── baseline-sha.txt
├── workflow-inventory.txt
├── action-ref-inventory.txt
├── dockerfile-inventory.json
└── unicode-format-control-scan.txt
```

Các inventory phải sinh từ Git object của baseline, không đọc từ danh sách viết tay trong tài liệu:

```bash
set -uo pipefail
AUDIT_DIR="docs/evidence/mandate-10/audit"
BASELINE_SHA="$(git rev-parse origin/main)"
mkdir -p "$AUDIT_DIR"
printf '%s\n' "$BASELINE_SHA" > "$AUDIT_DIR/baseline-sha.txt"
git ls-tree -r --name-only "$BASELINE_SHA" -- .github/workflows \
  | sort > "$AUDIT_DIR/workflow-inventory.txt"
git grep -nE '^[[:space:]-]*uses:[[:space:]]*' "$BASELINE_SHA" -- \
  '.github/workflows/*.yml' '.github/workflows/*.yaml' \
  | sort > "$AUDIT_DIR/action-ref-inventory.txt"

UNICODE_SCAN="$AUDIT_DIR/unicode-format-control-scan.txt"
if rg -n '\p{Cf}' docs/docx_cdo01/plan/mandate-10 -g '*.md' \
  > "$UNICODE_SCAN"; then
  echo "FAIL: hidden/format-control Unicode found" >&2
  exit 1
else
  scan_rc=$?
  test "$scan_rc" -eq 1 || exit "$scan_rc"
fi
```

Snapshot `bbe25038` sinh ra 7 workflow: `build-push-ecr`, `scan-external-images`, `secret-scan`, `terraform-plan`, `terraform-apply`, `validate-production-access`, `test-image-bump`. Con số này chỉ mô tả baseline trên, không phải mẫu số DoD cố định.

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

### Yêu cầu 6: 🟡 Implementation tồn tại; contract chưa được chứng minh

Workflow có `prepare` và `git diff`, nhưng sự tồn tại của code không đủ để gọi là đạt hoàn toàn. PM-131 phải có cả positive và negative contract tests:

- positive: đổi đúng một service thì chỉ service đó vào matrix, aggregate manifest và image-bump PR;
- positive: đổi shared/build input thì chọn đúng full set theo contract đã duyệt;
- negative: docs-only/no-op không build và vẫn tạo verdict rõ ràng;
- negative: changed service không map được, matrix rỗng trái kỳ vọng, service thừa, digest thiếu hoặc image-bump đổi ngoài scoped set đều fail closed;
- runtime evidence: link exact run ID/attempt, source SHA, selected set, skipped set, aggregate artifact và promotion PR.

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
5. Xóa duplicate gap analysis, chạy Unicode `Cf` gate và đính kèm machine-generated inventory cùng baseline SHA.
6. Rebase branch lên latest `main`, chạy lại audit/checks, đổi title/body PR và request review chỉ sau evidence đủ.

## 5. Review-blocker traceability

| Review blocker | Plan clause đóng blocker | Evidence để review lại |
|---|---|---|
| PM-124 chưa biết exact required contexts | §2 Yêu cầu 1 + PM-125 Admin/DoD | Ruleset/Branches export, exact context string, negative PR merge lock |
| Trivy/IaC workflow hiện tại không chạy PR | PM-125 PR-safe execution boundary + contract matrix | Read-only PR run, zero AWS/ECR write, aggregate result |
| Hai canonical gap-analysis | §0 canonical path | Repo inventory chỉ còn đúng một matching file |
| Hidden/bidirectional Unicode | §0 Unicode `Cf` gate | `unicode-format-control-scan.txt` rỗng và command exit 0 |
| Audit 6 workflow/action examples stale | §0 baseline + machine inventory; Yêu cầu 4 | Exact final-main SHA, workflow/action inventory artifacts |
| Scoped build bị gọi “đạt hoàn toàn” thiếu tests | Yêu cầu 6 | Positive/negative contract runs + selected/skipped sets + promotion PR |
| PM-129 thiếu authoritative/multi-arch/promotion/retention/ambiguity | PM-129 §0.1, §2.1–2.3, §4.1, §4.3–4.5 | Docker inventory JSON, platform descriptors, source+promotion PR, retained trace bundle |
| PM-132 dùng fake/nonexistent unsigned digest | PM-132 Demo 2 | ECR-resolvable digest, signature-absence proof, exact verifyImages rejection |

Một plan clause chỉ làm blocker **planned**, chưa làm nó `PASS`. Review blocker chỉ được đóng khi cột evidence tương ứng tồn tại và trỏ về exact baseline/run/PR.
