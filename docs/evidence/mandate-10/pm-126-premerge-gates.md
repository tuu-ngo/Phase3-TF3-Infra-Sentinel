# PM-126 pre-merge security gates

## Control statement

`.github/workflows/secure-delivery-gate.yml` runs on every pull request targeting `main` and on `merge_group`. It creates three child checks and one always-created aggregate job named exactly **`Secure delivery gate`**:

| Child check | Scope | Blocking policy | Artifact |
|---|---|---|---|
| IaC misconfiguration scan | `infra/live/production` and checked-in local modules | pinned tfsec, HIGH/CRITICAL threshold | `pm126-iac-<run>-<attempt>` |
| Repository secret scan | complete checked-out repository tree | pinned Trivy secret scanner; HIGH/CRITICAL evaluator | `pm126-secrets-<run>-<attempt>` (redacted only) |
| SAST scan | all primary service source under `phase3 - information/techx-corp-platform/src` | pinned Semgrep, `ERROR` maps to the PM-126 HIGH/CRITICAL blocking tier | `pm126-sast-<run>-<attempt>` |

The aggregate has `if: always()` and fails for any child result other than `success` (including cancelled or unexpected skipped). It is the only check the repo admin should mark required; the child checks are evidence-producing implementation details.

The workflow has only `contents: read`, checks out with `persist-credentials: false`, uses no repository/environment secret, and has no AWS OIDC, ECR login/push, image signing, Terraform apply or deployment path. It is safe for fork pull requests.

## Pre-merge/pre-push boundary

This workflow is the **pre-merge and pre-ECR-push** gate. The existing ECR scan-on-push in `build-push-ecr.yml` runs after a change reaches `main` and is a defense-in-depth release check; it is explicitly **not** used as evidence that a pull request was merge-blocked. A green ECR scan-on-push can never substitute for the required `Secure delivery gate` context.

Each scanner writes a parseable JSON/SARIF artifact with a 90-day retention period. Trivy's raw JSON is deleted after the redacted report is uploaded; match text and source code are never included in the retained secret artifact or aggregate summary.

## Immutable tool inputs

| Tool/action | Pin |
|---|---|
| tfsec | `aquasec/tfsec:v1.28.14@sha256:ac46d48a384ae2c0bbd0413cd2a18229e45e21a44d22c8be28b56de5b38d74c3` |
| Trivy | `aquasec/trivy:0.72.0@sha256:cffe3f5161a47a6823fbd23d985795b3ed72a4c806da4c4df16266c02accdd6f` |
| Semgrep | `semgrep/semgrep:1.170.0@sha256:c98f8829eea377274ee4b10656458b078b88232469b2ff913f091c2317347c9d` |
| checkout | `actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd` (v6.0.2) |
| upload-artifact | `actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02` (v4.6.2) |

## Local negative evidence (before PR publication)

These are disposable fixtures under `/tmp`, never committed and deleted after the run. The command exit codes are the gate evidence:

| Fixture | Expected result | Observed |
|---|---|---|
| Terraform security group egress `0.0.0.0/0` (`AVD-AWS-0104`, CRITICAL) | tfsec non-zero | `exit 1` |
| Synthetic `MANDATE10_TEST_SECRET_<32 chars>` | Trivy scan + evaluator non-zero | evaluator `exit 1`; redacted report has one HIGH and no `Match`/`Code` fields |
| Python `eval(user_input)` | Semgrep `ERROR` finding | `exit 1`; finding `pm126-python-dynamic-eval` |

Positive baseline evidence is recorded in `pm-126-tfsec-before-after.md`; the clean secret and SAST summaries were generated with the same pinned images and produced zero blocking findings.

## Admin handoff and merge-lock proof

The current execution identity cannot change branch protection/rulesets. After this workflow is merged, the repo owner/admin must:

1. Open a normal PR and confirm the exact check context **`Secure delivery gate`** appears.
2. Require only that exact context on `main`, with expected source GitHub Actions; keep existing review policy intact.
3. Export the resulting branch-protection/ruleset JSON (or equivalent settings export) into the PM-132 evidence bundle.
4. Open three disposable negative PRs (Terraform HIGH/CRITICAL, fake secret, SAST HIGH) and capture the red aggregate check plus the merge button locked. Do not merge the fixtures.

Until those admin actions and PR URLs/runs exist, PM-126 implementation is complete locally but the required-status-check and merge-lock DoD remains **pending external evidence**. No production apply or runtime change is needed for this handoff.
