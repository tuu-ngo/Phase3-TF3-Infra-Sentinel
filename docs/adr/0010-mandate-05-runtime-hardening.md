# ADR 0010 — Mandate 05: Runtime Admission Hardening

**Date:** 2026-07-17

**Decision owner:** CDO01 / TF3 Security

**Collaborators/reviewers:** TF3 platform owner, CDO02, mentor

**Status:** Accepted - Enforce cutover complete; mentor acceptance pending

## Context

Mandate 05 closes the remaining runtime admission gaps for `techx-tf3` without changing flagd, incident injection, or the public storefront boundary. The production chart is GitOps-managed through Argo CD, so policy changes must be introduced in Audit first, with exact exceptions documented before any Enforce step.

## Decision

1. Use the authoritative production render with all four Argo CD values files.
2. Stage Kyverno policies in Audit until each rule has an explicit test and
   evidence path, then promote one policy at a time with a live rejection and
   health gate.
3. Enforce CPU/memory resource requirements for containers and initContainers, but not ephemeral containers.
4. Enforce baseline security context for first-party workloads, with exact-label operational exceptions recorded in the exception register.
5. Enforce no-latest and first-party digest pinning separately from security policies.
6. Keep PM-101 signing and Trivy evidence as provenance input for first-party digest promotion.

## Scope

- Namespace: `techx-tf3`
- First-party application set: the 18 application workloads defined in the mandate spec.
- Operational/third-party workloads: handled separately with exact-label exceptions and review dates.

## Exceptions

Approved exceptions must be exact label matches, with an owner, reason,
remediation plan, and review date. Current exceptions are recorded in
`docs/evidence/mandate-05/exception-register.yaml` and are limited to:

- `kafka` init-container PVC ownership setup, which still requires root until a
  non-root ownership approach is validated; and
- `aiops-engine`, which is managed outside this GitOps tree and still lacks the
  required container-level baseline hardening.

## Rollback

- Resource policy rollback: revert the resource policy change only.
- Security policy rollback: revert the baseline policy change only.
- Image policy rollback: revert the latest/digest policy change only.
- Workload remediation rollback: revert the workload-only values change only.

## Cutover outcome

The four runtime policies are `Enforce` and `Ready=True` at source revision
`677e74b`. Argo CD, workload health, storefront, flagd and reconciled
PolicyReports remained clean through the one-policy-at-a-time cutover. The
admission evidence is recorded in
`docs/evidence/mandate-05/enforce-cutover-20260718.md`.

Mandate acceptance still requires the mentor rejection demonstration, final
PM-101 artifact packaging and final disposition of the two time-bounded
exceptions.

## Update 2026-07-21 — Native admission migration (PM-166/168/169/170)

Mentor rejected the Mandate 05 acceptance on the grounds that Kyverno is a
third-party admission tool, not a Kubernetes-native mechanism. This update
does not replace the decision above; it adds a native enforcement layer on
top of it and demotes Kyverno to a non-blocking role for the four rules it
previously enforced.

**Additional decisions:**

1. Replace Kyverno as the *blocking* mechanism for resource declarations and
   image-reference rules with native `ValidatingAdmissionPolicy`/CEL,
   matching `resources: ["pods"]` only (every controller-created object
   still results in a Pod admission request, so this avoids re-implementing
   Kyverno's per-kind autogen and the `Rollout` CRD coverage gap it once hit
   in PR #232).
2. Replace Kyverno's baseline security-context rule with Pod Security
   Admission `restricted` at the namespace level — this is more native than
   VAP itself (built into the API server, no CRD). PSA has no per-workload
   exception mechanism, unlike Kyverno's label-based `preconditions`; see
   Exceptions update below.
3. Kyverno is **not removed**. It keeps running, `Enforce`, unchanged, for
   two reasons: it still owns `verifyImages`/Cosign signature verification
   (PM-114/127/128, not something CEL can express — CEL cannot make an
   outbound network call at admission time) and background PolicyReport
   reconciliation (VAP is admission-time-only, it does not rescan existing
   resources). Removing the Kyverno controller is tracked separately as
   PM-172 and has not been authorized.
4. Cutover discipline for the two new native VAP bindings (image-reference,
   resource-requirements): observed dry-run gate before merge (5
   intentionally-violating fixtures under
   `docs/evidence/mandate-05/native-rejection-demo/`, all 18 live workloads
   checked for no false positive), landed in a single PR (#291) that carries
   both the `Warn/Audit` introduction and the promotion to `Deny` — by
   explicit user direction, there is no separately-observed live audit-bake
   window on the cluster this time (unlike the original Kyverno Enforce
   cutover, which staged each policy individually with a live health gate
   between Audit and Enforce). The pre-merge dry-run gate stands in for that
   step.
5. Pod Security Admission promotion (`audit`/`warn=restricted` →
   `enforce=restricted`) is staged separately and deliberately incomplete:
   namespace labels moved to `audit`/`warn=restricted` only.
   `enforce=restricted` is intentionally **not** set yet — see Exceptions
   update below.

**Exceptions — status update, native PSA has no equivalent to Kyverno's
label-based bypass:**

- `kafka` (`m05-baseline-kafka-init-chown`): in-cluster Kafka is retired per
  Mandate #8 (Kafka → MSK migration, confirmed complete by CDO02); the
  workload no longer serves production traffic and is pending deletion. No
  non-root remediation was attempted for it (a `fsGroup`-based approach was
  judged technically plausible — `values-prod.yaml` already sets
  `podSecurityContext.fsGroup: 1000` for kafka for an unrelated EBS
  permission issue — but not pursued, since the workload is being
  decommissioned rather than hardened). This exception is expected to close
  naturally once the in-cluster Kafka resources are deleted as part of
  Mandate #8 cleanup, not through a security fix.
- `aiops-engine` (`m05-baseline-aiops-engine-runtime`): confirmed to have no
  manifest anywhere in this GitOps repository — it is `kubectl apply`d
  directly by AIO02, outside ArgoCD. CDO01 has no file in this repo to edit
  to remediate it. Deferred to the workload owner; not blocking the rest of
  this migration.
- Because both exceptions remain live and unresolved at the runtime level
  (even though for well-understood reasons), PSA `enforce=restricted` stays
  off. This is a deliberate, documented gate, not an oversight — enabling it
  now would admission-reject any recreate/restart of either workload while
  it still runs with a root/privileged security context.

**Rollback additions:**

- Native image/resource policy rollback: change the affected
  `ValidatingAdmissionPolicyBinding.spec.validationActions` from `["Deny"]`
  back to `["Warn", "Audit"]`, or revert PR #291 through GitOps.
- LimitRange/ResourceQuota rollback: revert the `default`/`defaultRequest`
  removal and the quota increase through GitOps if headroom or debug-pod
  friction becomes a problem.
- PSA rollback: not applicable yet — `enforce` was never turned on.
- Kyverno retirement rollback: not applicable — Kyverno was never removed by
  this update.
