# PM-125 — Secure Delivery PR Gate Plan

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

For changed build targets, build local `linux/amd64` candidate images without pushing, scan with Trivy, and fail HIGH/CRITICAL according to the approved policy. Record the selected targets; no target may be treated as successful without a detected change set or an explicit no-image-change result.

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
| Một service đổi | Gitleaks + local build/Trivy đúng service | PASS/FAIL theo scan; không ECR write |
| Terraform đổi | Gitleaks + IaC | HIGH/CRITICAL fixture làm FAIL |
| Checkout/payment đổi | Gitleaks + SAST + Trivy nếu build input đổi | Fixture làm FAIL |
| Shared build/workflow đổi | Tập target theo contract đã duyệt | Không được matrix rỗng/silent PASS |
| Child fail/cancel/unexpected skip | Control tương ứng applicable | FAIL |
| Fork PR | Cùng read-only contract, zero secret/AWS | Deterministic PASS/FAIL, không privileged fallback |

## Admin and proof steps

1. Export/screenshot current `main` ruleset/branch protection and exact required contexts.
   Record whether merge queue is enabled and whether `merge_group` is required.
2. Land the workflow; confirm `Secure delivery gate` appears on a normal PR and a Terraform/code PR.
3. Require only the aggregate context in ruleset, avoiding path-filtered child contexts.
4. Open disposable negative PRs: fake secret, Terraform misconfiguration, a known-safe reproducible Trivy finding fixture, and SAST fixture. Capture failed aggregate check and merge lock. Never merge fixtures.
5. Link workflow runs, ruleset export, PR screenshots and logs from PM-132 evidence.

## Definition of Done

- [ ] Aggregate `Secure delivery gate` runs on every PR and is the required context.
- [ ] Gitleaks, PR-mode Trivy, IaC and SAST results are correctly evaluated when applicable.
- [ ] Unchanged Terraform or money-path source does not leave a required check pending/skipped.
- [ ] A negative PR proves a failed aggregate gate locks merge.
- [ ] Workflow permissions prove zero AWS/ECR/production write path, including fork PR behavior.
- [ ] Admin export records the exact required context string; a screenshot showing only “successful check” is insufficient.
- [ ] Actions/tool downloads are immutable-pinned before final evidence (PM-129).
