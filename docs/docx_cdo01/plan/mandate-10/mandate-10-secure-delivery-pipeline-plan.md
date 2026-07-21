# PM-125 — Secure Delivery PR Gate Plan

**Master sequence:** `mandate-10-closure-execution-plan.md` Gate 1.

## Objective

Close the PR-mode security-gate gap without making required checks permanently pending or skipped. Current Trivy image scanning is release-time only (`push main`/manual); it cannot block a PR before merge.

## Required-check architecture

Do **not** make a path-filtered IaC/SAST job an individual required check. On a PR that does not touch its path, GitHub can mark that check skipped/pending and block merge unpredictably.

Create one workflow with a stable, always-created check named **`Secure delivery gate`**:

```text
Secure delivery gate
├── detect changes
├── Gitleaks
├── PR-mode image build + Trivy scan
├── IaC scan only when Terraform changes
├── SAST only when checkout/payment changes
└── final aggregate job: always runs, evaluates every applicable result
```

Branch protection/ruleset must require only `Secure delivery gate` (plus existing approved-review policy and independently confirmed checks). The aggregate job uses `if: always()` and fails if an applicable child job fails, is cancelled, or is unexpectedly skipped; a non-applicable IaC/SAST job is explicitly recorded as not-applicable rather than silently treated as pass.

## Required-gate trust boundary

Repo hiện thuộc user account, nên PM-125 không giả định organization-level required workflow. Required gate chỉ được coi là trusted khi:

- `.github/CODEOWNERS` bảo vệ chính CODEOWNERS, `.github/workflows/**`, `scripts/ci/**`, `scripts/security/**`, `gitops/policies/kyverno/**`, `infra/modules/eks-platform/**` và `docs/evidence/mandate-10/**` bằng một principal thật có write access;
- ruleset yêu cầu code-owner approval từ người khác author, dismiss stale approvals, approval cho most recent reviewable push, strict up-to-date branch và chặn direct/force push;
- required context `Secure delivery gate` chọn expected source là GitHub Actions App;
- repo-wide check bảo đảm không workflow/job thứ hai tạo cùng check name;
- bypass list rỗng, hoặc exception có ticket, owner, expiry và ruleset audit export.

CODEOWNER principal phải được admin chốt trước implementation; placeholder không được merge. Nếu repo chuyển vào organization hỗ trợ required workflows, có thể nâng trust root sang workflow từ security-controls repository riêng qua ADR.

Governance negative test phải sửa aggregate thành unconditional PASS hoặc tạo duplicate job name. PR đó phải bị block nếu chưa có fresh security-owner approval; fixture không được merge.

## Current-state constraints

- Branch-protection required contexts must be confirmed by repo admin through Settings/Rulesets; PR metadata and a non-admin API 404 are not evidence.
- `secret-scan.yml` runs Gitleaks on PRs. It can only block merge after its exact check context is required.
- `build-push-ecr.yml` does not have `pull_request`; its Trivy gate blocks release after merge, not the PR.
- IaC and SAST are not yet evidenced as final-main PR gates.

## PR-safe execution boundary

PM-125 phải tạo gate riêng cho PR; không thêm `pull_request` trực tiếp vào release/provisioning workflow hiện tại.

Required PR workflow phải:

- khai báo tối đa `permissions: contents: read`; không có `id-token: write`, `packages: write`, `pull-requests: write` hoặc quyền deployment;
- checkout với `persist-credentials: false`, không dùng repository/environment secret và không assume AWS role;
- không ECR login/push, không `cosign sign`, không mở image-bump PR, không chạy Terraform apply và không ghi production artifact;
- build candidate vào local BuildKit only; Trivy/IaC/SAST đọc source của PR và xuất artifact/log không chứa secret;
- chạy an toàn cho fork PR. Nếu một control không thể chạy trên fork mà không có secret, aggregate phải fail/mark blocked theo policy đã duyệt, không chuyển sang `pull_request_target` để chạy code không tin cậy với secret;
- pin action/tool theo PM-129 trước khi context được cấu hình required.

Release workflows `build-push-ecr.yml`, `terraform-plan.yml` và `terraform-apply.yml` giữ production boundary riêng. Kết quả post-merge của chúng không được dùng thay bằng chứng PR merge gate.

## Implementation design

### 1. Detect changes

Run on every `pull_request` to `main`. Admin evidence must also confirm whether merge queue is enabled. If it is enabled, the required workflow must additionally trigger on `merge_group`; otherwise a required Actions workflow can be missing from the merge-queue validation commit. Emit booleans for Terraform production/modules, checkout/payment source, Dockerfile/build context and all CI workflow changes. The final aggregate job always consumes the emitted values.

```yaml
on:
  pull_request:
  merge_group: # required when repository merge queue is enabled
```

### 2. Gitleaks

Run on every PR. Reuse the existing policy or call it from the aggregate workflow; do not create two contradictory required contexts.

### 3. PR-mode image + Trivy

For changed build targets, create a matrix over every selected service and both `linux/amd64` and `linux/arm64`. Build local/OCI candidates without pushing, scan each platform with Trivy, and fail HIGH/CRITICAL according to the approved policy. QEMU/Buildx is allowed; AWS OIDC, ECR login/push, signing and promotion are forbidden.

The aggregate compares the expected `(service, platform)` set with parseable report artifacts. A missing AMD64/ARM64 report, failed/cancelled/unexpected-skipped matrix cell, duplicate cell or empty matrix contrary to the change contract fails closed. Release workflow still rescans exact pushed digests after merge.

### 4. Conditional IaC and SAST

- IaC: scan `infra/live/production` and `infra/modules` when Terraform/workflow changes affect it; fail high/critical misconfiguration.
- SAST: scan checkout and payment when those paths change; use approved pinned tooling and severity policy.
- Neither path-specific job is configured directly as a required context.

### 5. Aggregate verdict

The `Secure delivery gate` checks matrix outputs, not only exit codes. It must fail on relevant job failure/cancellation/unexpected skip and publish a concise summary of applicable/non-applicable controls. Its workflow name/job name are stable before ruleset configuration.

### 6. Contract test matrix

| Case | Expected applicable controls | Expected aggregate |
|---|---|---|
| Docs-only PR | Gitleaks; IaC/SAST/Trivy explicit N/A | PASS, check vẫn được tạo |
| Một service đổi | Gitleaks + local build/Trivy AMD64 và ARM64 đúng service | PASS/FAIL theo cả hai scan; không ECR write |
| Terraform đổi | Gitleaks + IaC | HIGH/CRITICAL fixture làm FAIL |
| Checkout/payment đổi | Gitleaks + SAST + Trivy nếu build input đổi | Fixture làm FAIL |
| Shared build/workflow đổi | Tập target theo contract đã duyệt | Không được matrix rỗng/silent PASS |
| Child fail/cancel/unexpected skip | Control tương ứng applicable | FAIL |
| Fork PR | Cùng read-only contract, zero secret/AWS | Deterministic PASS/FAIL, không privileged fallback |
| Gate/workflow/security script đổi | Gitleaks + integrity controls + applicable scans | Fresh security-owner approval bắt buộc |
| Aggregate bị sửa luôn PASS/job trùng tên | Governance fixture | PR bị block; không được merge |

## Admin and proof steps

1. Export/screenshot current `main` ruleset/branch protection and exact required contexts.
   Record whether merge queue is enabled and whether `merge_group` is required.
2. Land the workflow; confirm `Secure delivery gate` appears on a normal PR and a Terraform/code PR.
3. Add CODEOWNERS and verify the selected principal resolves; enable code-owner/latest-push/stale-review controls before trusting the gate.
4. Require only the aggregate context in ruleset, select GitHub Actions as expected source, and prove the check name is unique repo-wide.
5. Open disposable negative PRs: fake secret, Terraform misconfiguration, known-safe reproducible AMD64/ARM64 Trivy fixtures, SAST fixture and malicious aggregate/duplicate-name changes. Capture failed aggregate/governance gate and merge lock. Never merge fixtures.
6. Link workflow runs, ruleset export, PR screenshots and logs from PM-132 evidence.

## Definition of Done

- [ ] Aggregate `Secure delivery gate` runs on every PR and is the required context.
- [ ] Gitleaks, dual-platform PR-mode Trivy, IaC and SAST results are correctly evaluated when applicable.
- [ ] Unchanged Terraform or money-path source does not leave a required check pending/skipped.
- [ ] A negative PR proves a failed aggregate gate locks merge.
- [ ] Workflow permissions prove zero AWS/ECR/production write path, including fork PR behavior.
- [ ] Admin export records the exact required context string; a screenshot showing only “successful check” is insufficient.
- [ ] CODEOWNERS, fresh non-author owner approval, stale-review dismissal, unique check name and expected GitHub Actions source are proven.
- [ ] A malicious gate-edit/duplicate-name PR cannot merge without the governance controls.
- [ ] Actions/tool downloads are immutable-pinned before final evidence (PM-129).
