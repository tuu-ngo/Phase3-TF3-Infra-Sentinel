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

## Implementation design

### 1. Detect changes

Run on every `pull_request` to `main`. Emit booleans for Terraform production/modules, checkout/payment source, Dockerfile/build context and all CI workflow changes. The final aggregate job always consumes the emitted values.

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

## Admin and proof steps

1. Export/screenshot current `main` ruleset/branch protection and exact required contexts.
2. Land the workflow; confirm `Secure delivery gate` appears on a normal PR and a Terraform/code PR.
3. Require only the aggregate context in ruleset, avoiding path-filtered child contexts.
4. Open disposable negative PRs: fake secret, Terraform misconfiguration, a known-safe reproducible Trivy finding fixture, and SAST fixture. Capture failed aggregate check and merge lock. Never merge fixtures.
5. Link workflow runs, ruleset export, PR screenshots and logs from PM-132 evidence.

## Definition of Done

- [ ] Aggregate `Secure delivery gate` runs on every PR and is the required context.
- [ ] Gitleaks, PR-mode Trivy, IaC and SAST results are correctly evaluated when applicable.
- [ ] Unchanged Terraform or money-path source does not leave a required check pending/skipped.
- [ ] A negative PR proves a failed aggregate gate locks merge.
- [ ] Actions/tool downloads are immutable-pinned before final evidence (PM-129).
