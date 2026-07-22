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

## Live required-gate rejection evidence

On 2026-07-23 the repo owner enabled the exact GitHub Actions context **`Secure delivery gate`** as a required check for `main`. `gh pr checks <PR> --required` reports the failed aggregate as required on each disposable PR, and the GitHub merge state is `BLOCKED`.

| Control | Disposable PR | Intended failed child | Required aggregate evidence | Merge state |
|---|---|---|---|---|
| IaC CRITICAL | [#350](https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel/pull/350) | [IaC misconfiguration scan](https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel/actions/runs/29941763818/job/88997124650) | [Secure delivery gate](https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel/actions/runs/29941763818/job/88997235173) | `BLOCKED` |
| Synthetic secret HIGH | [#351](https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel/pull/351) | [Repository secret scan](https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel/actions/runs/29941768360/job/88997138937) | [Secure delivery gate](https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel/actions/runs/29941768360/job/88997237922) | `BLOCKED` |
| SAST HIGH | [#352](https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel/pull/352) | [SAST scan](https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel/actions/runs/29941770620/job/88997146205) | [Secure delivery gate](https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel/actions/runs/29941770620/job/88997251333) | `BLOCKED` |

The scanner children not under test passed on each PR, isolating the intended rejection. These fixture PRs and branches are evidence only and must never be approved or merged.

## Admin handoff status

Completed:

1. The workflow was merged by [PR #348](https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel/pull/348) at `main@4d4e66de5fff1d87cc194b23ad227e5c976f993b`.
2. The exact `Secure delivery gate` context is required on `main`.
3. Three real negative PRs fail the intended child, fail the required aggregate and report `mergeStateStatus=BLOCKED`.

Pending owner-only artifact:

1. Export the final Branch protection or Ruleset configuration into the PM-132 evidence bundle. The current non-admin identity can verify the required context and blocked PRs but receives HTTP 404 from the branch-protection export API.

No production apply or runtime change is needed for this handoff. The post-merge Terraform Plan succeeded, but its bastion replacement remains under a separate no-apply safety hold.
