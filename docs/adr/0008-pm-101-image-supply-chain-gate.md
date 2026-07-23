# ADR 0008 — PM-101: Trivy release gate and keyless image signing

**Date:** 2026-07-16

**Decision owner (signed):** nvtank — PM-101 implementer / commit author

**Collaborators/reviewers:** TF3 Platform Security; mentor approval pending

**Status:** Accepted in branch; production evidence pending merge and first full
workflow run on `main`

**Pillars:** Security (primary), Operational Excellence and Auditability

## Context

PM-95 already made the ECR repository immutable and moved deployment inventory
toward digest pinning. ECR `scanOnPush=true`, however, scans only after an image
has reached the registry. The existing build workflow pushed images before its
Trivy check and did not sign them, so it could neither stop a vulnerable
candidate before push nor prove that a running digest came from the TF3 release
workflow.

The control must add no cluster service or fixed infrastructure cost, must not
change the public/private endpoint boundary, and must not alter flagd or any
incident-injection mechanism.

## Decision

1. Every selected first-party build target is built locally for the EKS runtime
   architecture (`linux/amd64`) and scanned before the normal ECR push.
2. The release threshold is zero `HIGH` and zero `CRITICAL` vulnerabilities,
   including unfixed findings. Trivy exits non-zero when this threshold is
   exceeded, so subsequent push and signing steps do not run.
3. The workflow uploads one JSON Trivy report per selected target, including
   reports produced before a failed gate, and retains them for 90 days.
4. After a clean gate, the workflow pushes the multi-architecture manifest,
   resolves its immutable ECR digest, and signs that digest with Cosign keyless
   signing through GitHub Actions OIDC. No long-lived signing key is stored.
5. The workflow immediately verifies each signature against the GitHub OIDC
   issuer and exact workflow identity. It uploads the raw verification reports
   and a mapping from service, Git SHA and Actions run to digest and scan/sign
   evidence.
6. Third-party images are not signed with the TF3 identity. They are explicit
   exceptions, remain digest-pinned, and receive a scheduled non-blocking Trivy
   review because TF3 does not own their build provenance.
7. Admission-time signature verification is deferred to the Kyverno task. Until
   that control is audited and safely enforced, only digests with complete CI
   evidence may be promoted through a separate GitOps PR.

## Alternatives considered

- **Rely on ECR scan-on-push:** rejected because detection happens after the
  candidate is already in ECR and does not provide build provenance.
- **Use a static Cosign key in GitHub Secrets:** rejected because key rotation,
  leakage and custody create avoidable operational risk; GitHub OIDC provides a
  short-lived identity tied to the workflow.
- **Require TF3 signatures on upstream images:** rejected because signing an
  artifact TF3 did not build would make the provenance claim misleading.
- **Enable admission enforcement in the same change:** rejected for this task
  because current images have no TF3 signatures. Immediate enforcement could
  block legitimate rollouts before the signed inventory exists.

## Consequences and trade-offs

### Positive

- A first-party image with an unreviewed HIGH/CRITICAL finding cannot reach the
  normal push step.
- Every successfully released digest can be traced to a Git commit, workflow
  identity, scan report and successful signature verification.
- The solution uses existing GitHub Actions and ECR capabilities and creates no
  additional in-cluster service or fixed AWS cost.
- This produces the trust material required for a later Kyverno verify-images
  policy.

### Negative / residual risk

- The local candidate build plus the later multi-platform build increases CI
  time and GitHub Actions consumption.
- The strict zero threshold can block releases until dependencies are patched
  or Security records an explicit time-bounded exception.
- The pre-push scan covers `linux/amd64`, which is the current EKS runtime. The
  additionally published `linux/arm64` variant is not independently scanned.
- Merge alone is not proof of completion: ECR signatures and per-running-image
  evidence exist only after a successful full run and controlled GitOps
  promotion.

## Rollout and admission transition

1. Merge only this isolated CI/docs branch.
2. Run the build workflow in full mode on `main`; remediate findings until all
   required first-party targets pass and are signed.
3. Retain both scan and signed-release artifacts, then promote only recorded
   digests in a separate GitOps PR.
4. Compare live pod digests with the signed evidence.
5. Introduce Kyverno signature verification in audit mode, review violations
   and the external-image exception set, then move to enforce only after the
   live first-party inventory has zero unexplained violations.

This sequence has no direct pod rollout at steps 1-2, so it does not interrupt
the storefront or change the operational exposure boundary.

## Rollback

Revert the PM-101 merge commit to restore the previous CI workflow. This does
not restart workloads, mutate deployed digests, change ECR immutability, expose
private endpoints, or affect flagd. Existing signatures and retained evidence
remain harmless audit artifacts.

## Evidence

Implementation and before/after evidence are recorded in
[`pm-101-image-supply-chain.md`](../evidence/pm-101-image-supply-chain.md).
The ADR remains production-evidence pending until all unchecked items in that
record are completed.

---

*Signed: nvtank, PM-101 implementation owner, 2026-07-16. Mentor/Platform
Security acceptance to be recorded against the PR and first full workflow run.*
