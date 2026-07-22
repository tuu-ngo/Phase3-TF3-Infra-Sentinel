# Mandate 10 - PR security gate plan for IaC and SAST

Date: 2026-07-21

## Scope

This plan covers the PR-gate part of Mandate 10 for this task:

- confirm the exact required status checks on `main`;
- add IaC misconfiguration scan for Terraform production;
- add SAST for checkout/payment;
- make the new security checks block merge reliably;
- prove the block with a disposable red PR.

This plan does not close the whole Mandate 10 by itself. SBOM, Cosign provenance, digest pinning, native Kubernetes admission enforcement with `ValidatingAdmissionPolicy`/VAP, and full pod provenance are tracked by the other Mandate 10 tasks.

## Target Design

Use one stable required check named:

```text
Secure delivery gate
```

Do not make `IaC scan` or `SAST` path-filtered jobs required directly. Path-filtered required checks can become skipped or missing on unrelated PRs, which can block merges unpredictably or create confusing evidence.

The aggregate gate should always be created on PRs to `main`:

```text
Secure delivery gate
+-- detect changed areas
+-- IaC scan, if Terraform paths changed
+-- SAST, if checkout/payment paths changed
+-- aggregate verdict, always runs
```

Branch protection should require the new aggregate context `Secure delivery gate`, plus the existing review requirement and independently confirmed build/Trivy/secret checks.

## Why This Design

Mandate 10 requires "red CI = no merge, no deploy". That means the required check must exist on every relevant PR and must fail closed when an applicable security control fails, is cancelled, or is unexpectedly skipped.

A stable aggregate gate gives the repository one required context that GitHub can enforce consistently. Conditional child jobs can still run only when their paths are relevant, but the final gate records whether each control was `pass`, `fail`, or `not applicable`.

## Current State To Confirm

Branch protection on `main` is already known to exist from PR #273 evidence. Do not spend time "enabling" it again.

Still required:

- admin screenshot/export of `Settings -> Branches` or Rulesets for `main`;
- exact list of current required status checks;
- confirmation whether merge queue is enabled;
- confirmation whether current required checks include Gitleaks, Trivy, IaC, and SAST.

Do not use the old non-admin API 404 as evidence. GitHub can return 404 when the token lacks admin visibility.

## Implementation Steps

### Step 1 - Capture admin evidence

What to do:

- Ask a repo admin to open branch protection/ruleset settings for `main`.
- Capture screenshot/export of exact required status checks.
- Record whether merge queue is enabled.
- Save this evidence under `docs/evidence/mandate-10/`.

Expected output:

- Before-update required-check evidence.
- A list of checks that must be added or replaced by `Secure delivery gate`.

Why:

Workflow YAML only proves that a job exists. It does not prove GitHub blocks merge on that job. Mandate 10 needs proof of enforcement, not assumptions.

### Step 2 - Add one aggregate PR workflow

What to do:

- Add a new workflow, for example:

```text
.github/workflows/secure-delivery-gate.yml
```

- Trigger it on:

```yaml
pull_request:
  branches: [main]
merge_group:
```

- Keep `merge_group` if merge queue is enabled. If merge queue is confirmed disabled, document that decision.
- Give the final aggregate job a stable name:

```text
Secure delivery gate
```

Expected output:

- Every PR to `main` creates `Secure delivery gate`.
- The check exists even when IaC/SAST paths are not changed.

Why:

This avoids skipped required checks. It also gives the admin one stable check name to add to branch protection.

### Step 3 - Detect changed areas

What to do:

- Add a `detect-changes` job.
- Detect these booleans:

```text
terraform_changed = infra/live/production/** OR infra/modules/** OR secure-delivery workflow changed
money_path_changed = phase3 - information/techx-corp-platform/src/checkout/** OR phase3 - information/techx-corp-platform/src/payment/** OR secure-delivery workflow changed
image_path_changed = service Dockerfile/build context changed
```

- Use either `git diff` against PR base or a pinned paths-filter action after action-pinning work is complete.

Expected output:

- The aggregate job knows which controls are applicable.
- Workflow changes force IaC/SAST to run, so the gate cannot be weakened silently.

Why:

IaC and SAST should not run as required checks on every PR if their code did not change, but security workflow changes must always test the gate itself.

### Step 4 - Reconcile existing secret and Trivy checks

What to do:

- Keep `secret-scan.yml` as the Gitleaks source of truth unless the admin evidence shows a reason to fold it into this workflow.
- Confirm the exact Gitleaks check context and ask admin to require it if it is not already required.
- Confirm whether any Trivy check currently runs on PRs and can be required.
- If Trivy only runs after merge in `build-push-ecr.yml`, record it as a remaining PR-mode Trivy gap or add PR-mode Trivy in a follow-up task.

Expected output:

- Secret scan is required through its existing check or explicitly tracked as not yet required.
- Trivy required-check status is proven by admin evidence, not guessed.

Why:

This task adds the missing IaC/SAST gates. Secret and Trivy already have workflow coverage in the repo, but they only satisfy Mandate 10 when GitHub branch protection actually requires their exact check contexts.

### Step 5 - Add IaC misconfiguration scan

Recommended tool:

- Use tfsec for Terraform scanning in this task.

What to scan:

```text
infra/live/production
infra/modules
```

When to run:

- Run when `terraform_changed == true`.
- Also run when the secure-delivery workflow itself changes.

Suggested behavior:

- framework: Terraform
- output: CLI output, plus JSON/SARIF artifact later if convenient
- fail with `--minimum-severity HIGH`, which covers HIGH and CRITICAL
- no AWS credentials required for PR scan

Expected output:

- Terraform HIGH/CRITICAL misconfig makes the IaC job fail.
- Aggregate `Secure delivery gate` fails when IaC is applicable and fails.
- Non-Terraform PRs record IaC as `not applicable`, not skipped silently.

Why:

`terraform plan` catches syntax/state drift, but not security posture like public exposure, weak IAM, disabled encryption, or unsafe network rules. IaC scan must run before merge because infrastructure defects become real once applied.

### Step 6 - Add SAST for checkout/payment

Recommended coverage:

- `gosec` for Go checkout service.
- Semgrep for checkout/payment source, especially payment JavaScript.

Paths:

```text
phase3 - information/techx-corp-platform/src/checkout/**
phase3 - information/techx-corp-platform/src/payment/**
```

When to run:

- Run when `money_path_changed == true`.
- Also run when the secure-delivery workflow itself changes.

Suggested behavior:

- checkout: run `gosec ./...` from the checkout service directory.
- payment: run Semgrep against the payment service directory.
- fail on HIGH findings.
- upload logs/SARIF/JSON as evidence when possible.

Expected output:

- A deliberate HIGH SAST fixture in checkout/payment makes SAST fail.
- Aggregate `Secure delivery gate` fails when SAST is applicable and fails.
- Non-money-path PRs record SAST as `not applicable`.

Why:

Checkout/payment are the money path. A basic SAST gate prevents obvious high-impact code issues from reaching signed images and production deployment.

### Step 7 - Record PR-mode Trivy status

What to do:

- Confirm whether Trivy is already a required PR check.
- If current Trivy only runs in `build-push-ecr.yml` on `push main` or `workflow_dispatch`, do not claim it is a PR merge gate.
- Either add a PR-mode Trivy follow-up, or document that the current task closes IaC/SAST while Trivy PR-mode remains owned by another Mandate 10 task.

Expected output:

- The final evidence does not confuse release-time Trivy with PR-time required checks.

Why:

Mandate 10 says scan before cluster and block before delivery. A scan that only runs after merge cannot prove "red CI = no merge".

### Step 8 - Implement the aggregate verdict

What to do:

- Final job name must be exactly stable, for example:

```text
Secure delivery gate
```

- Use `if: always()` on the aggregate job.
- Fail if an applicable child job:
  - failed;
  - was cancelled;
  - was skipped unexpectedly;
  - did not publish the expected status output.
- Pass only when every applicable control passes.
- Print a concise summary:

```text
Gitleaks: pass
Trivy: not applicable
IaC: pass
SAST: fail
Overall: fail
```

Expected output:

- Reviewer can understand why the gate passed or failed from the summary.
- GitHub branch protection only needs one required check context.

Why:

This is the core best practice. It removes ambiguity from conditional jobs and makes the required status check reliable.

### Step 9 - Update branch protection

What to do:

- After the aggregate workflow has appeared on at least one PR, ask admin to add `Secure delivery gate` to required status checks.
- Remove direct path-filtered IaC/SAST required contexts if they were added.
- Keep required review policy.
- Capture screenshot/export after update.

Expected output:

- Required checks show `Secure delivery gate`.
- Evidence shows the required context name exactly.

Why:

GitHub can only require checks that have existed before. The admin should add the stable aggregate check after it has run once.

### Step 10 - Prove with disposable red PRs

What to do:

- Create disposable negative PRs. Do not merge them.
- Test at least:
  - Terraform HIGH/CRITICAL misconfiguration.
  - SAST HIGH finding in checkout/payment.
  - Secret fixture if Gitleaks is part of aggregate evidence.
  - Trivy fixture if PR-mode Trivy is in scope.
- Capture:
  - failed child job;
  - failed `Secure delivery gate`;
  - GitHub merge blocked UI;
  - exact required check list.

Expected output:

- Red security control blocks merge through `Secure delivery gate`.

Why:

This is the mentor-verifiable proof. A plan or workflow is not enough; the repository must show a failing required security gate locks merge.

## Evidence Package

Save under:

```text
docs/evidence/mandate-10/
```

Required evidence:

- before-update branch protection/ruleset screenshot or export;
- PR link showing `Secure delivery gate` exists;
- after-update branch protection/ruleset screenshot or export;
- IaC red PR link, run link, log, and merge-block screenshot;
- SAST red PR link, run link, log, and merge-block screenshot;
- admin evidence for build/Trivy/secret required contexts, or explicit note that a separate task must add missing PR-mode coverage;
- final workflow file diff.

## DoD Checklist

- [ ] Admin evidence confirms current required checks on `main`.
- [ ] `Secure delivery gate` runs on every PR to `main`.
- [ ] `merge_group` handling is included or explicitly ruled out by admin evidence.
- [ ] IaC scan covers `infra/live/production` and `infra/modules`.
- [ ] IaC HIGH/CRITICAL fails the aggregate gate.
- [ ] SAST covers checkout/payment.
- [ ] SAST HIGH fails the aggregate gate.
- [ ] Non-applicable IaC/SAST jobs do not leave required checks pending or missing.
- [ ] Branch protection requires `Secure delivery gate`.
- [ ] Disposable red PR proves merge is blocked.
- [ ] Evidence is linked in `docs/evidence/mandate-10/`.

## Notes For Reviewers

- This plan intentionally uses an aggregate required check instead of requiring IaC/SAST child jobs directly.
- This task should not claim all of Mandate 10 is complete.
- New actions, reusable workflows, container images, and downloaded CLI tools introduced by this task must be pinned according to the Mandate 10 immutable-dependency task before final evidence.
- SBOM, provenance trace, action SHA pinning, Docker digest pinning, and VAP-based admission enforcement must be closed by their own evidence tasks before final Mandate 10 closure.
- Do not use real secrets, AWS keys, flagd tokens, or production credentials in negative fixtures.
