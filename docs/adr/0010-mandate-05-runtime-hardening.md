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
- **Third, previously-unregistered gap found via live `--dry-run=server`
  test (2026-07-21):** the DaemonSet `otel-collector-agent` — the shared
  OpenTelemetry Collector running on every node, used by all 18 services —
  also violates `restricted` (6 `hostPort` container ports plus a
  `hostPath` volume, neither allowed under `restricted`). This is now the
  primary blocker for `enforce=restricted`, not just the two registered
  exceptions: its blast radius is cluster-wide (any node replacement,
  drain, or DaemonSet rollout strands that node's collector), larger than
  either single-workload exception. Remediation has not been scoped yet.
  Full detail: `docs/evidence/mandate-05/native-migration-20260721.md`.

**Rollback additions:**

- Native image/resource policy rollback: change the affected
  `ValidatingAdmissionPolicyBinding.spec.validationActions` from `["Deny"]`
  back to `["Warn", "Audit"]`, or revert PR #291 through GitOps.
- ResourceQuota rollback: revert the quota increase through GitOps if headroom
  or debug-pod friction becomes a problem.
- PSA rollback: not applicable yet — `enforce` was never turned on.
- Kyverno retirement rollback: not applicable — Kyverno was never removed by
  this update.

## Update 2026-07-21 — LimitRange defaulting hotfix

Post-merge verification of PR #291 showed `bad-missing-resources-pod.yaml` was
still admitted. Kubernetes `LimitRanger` materialized `default` and
`defaultRequest` from the configured Container `LimitRange.max` values, so the
native resource VAP evaluated an already-mutated Pod instead of the user's
original object.

Decision: remove `gitops/infrastructure/limit-range.yaml` from GitOps. The
native enforcement path is now VAP for explicit per-Pod resources plus
ResourceQuota for namespace-level budget and capacity guardrails. Do not
reintroduce a Container `LimitRange` with `default`, `defaultRequest`, `min`, or
`max` unless explicit-resource enforcement is moved to a pre-mutation control;
otherwise omitted resources can be silently filled before VAP evaluates.

Rollback caveat: re-adding the old LimitRange can make
`bad-missing-resources-pod.yaml` pass again, so it is not a safe rollback for
Mandate 05 acceptance unless the VAP resource policy is first disabled or
redesigned.

## Update 2026-07-21 — Otel host metrics node-agent split

PR3 of the OpenTelemetry PSA migration adds a dedicated `otel-node-agent`
DaemonSet in a new `observability-system` namespace. This agent is intentionally
limited to host/kubelet metrics and exports them to Prometheus over OTLP HTTP.
It does not receive application OTLP traffic, expose receiver hostPorts, or
replace the existing `otel-collector-agent` yet.

Decision:

- Keep application telemetry on the `otel-gateway` Deployment introduced by PR1
  and selected by PR2.
- Keep the old `otel-collector-agent` DaemonSet live as fallback until the new
  node-agent is observed receiving/exporting host and kubelet metrics.
- Isolate the unavoidable host metrics `hostPath: /` requirement into
  `observability-system`, labelled `audit`/`warn=baseline`, instead of trying to
  force `techx-tf3` to `enforce=restricted` while a node-level collector still
  needs host filesystem access.
- Open Prometheus ingress explicitly for `observability-system` pods labelled
  `app.kubernetes.io/name=otel-node-agent`; otherwise the node-agent can become
  Ready but fail to deliver metrics.

This is an additive, no-cutover change. PSA `enforce=restricted` for
`techx-tf3` remains blocked until the old hostPort/hostPath collector, Kafka,
and `aiops-engine` exceptions are resolved. The next safe gate after this PR is
live comparison of old collector host metrics versus `otel-node-agent` metrics;
only then can the old DaemonSet's host metrics responsibilities be retired.

## Update 2026-07-22 — PSA `enforce=restricted` live, Kyverno retired (PM-172), Mandate 5 fully native

**Status:** Accepted — native admission enforcement (VAP + PSA) is the sole blocking mechanism in `techx-tf3`. Kyverno controller removed. Mentor demo re-run and passed under the fully-native architecture (see evidence below). **Signed:** CDO01 (Hoàng Trọng Tân), 22/07/2026. *(Mentor countersignature — pending, add name/date here once witnessed.)*

### Decision

1. `ValidatingAdmissionPolicy` bindings (`mandate05-native-image-reference`, `mandate05-native-resource-requirements`) — unchanged, confirmed still `Deny` and functioning (live since PR #291).
2. Enable `pod-security.kubernetes.io/enforce=restricted` on `techx-tf3` (PR #338) — the last native control still in audit-only mode is now blocking for real. Gate conditions required before enabling, all independently verified (not taken on faith):
   - `otel-collector-agent` (the hostPort/hostPath blocker from the section above): closed by proving `otel-node-agent` + `otel-gateway` have full receiver/extension parity (PR #332/#335/#336), then disabling the old DaemonSet (PR #337) and confirming **0 real spans/metrics** (self-telemetry excluded) reaching it for 2+ minutes before cutover.
   - Kafka legacy (root init-container blocker): confirmed removed via `git log` (PR #324), not just accepted as reported — 0 pods/PVCs live.
   - `aiops-engine`: remains the **one accepted, open exception** (see Exceptions update below) — not blocking Mandate 5 acceptance, tracked separately with AIO02 as owner.
3. Retire Kyverno entirely (PM-172, previously gated pending explicit go-ahead — greenlit by user 22/07 after (1) and (2) above were both proven live with full parity, closing the reason Kyverno was originally kept as a safety net for these specific rules):
   - Step 1 (PR #339): all 4 `ClusterPolicy` downgraded `Enforce → Audit` (non-blocking checkpoint).
   - Step 2 (PR #340): `kyverno-policies` Argo app + 4 `ClusterPolicy` manifests removed from git.
   - Step 3 (PR #341): `kyverno` Argo app (controller, webhooks, CRDs) removed from git.
   - **Explicitly accepted trade-off:** Kyverno was also the only path to Cosign `verifyImages` admission-time verification (PM-114/127/128) and PolicyReport background reconciliation for existing-resource drift — neither VAP nor PSA replace these. Per this repo's last status, `verifyImages` was not yet actually wired into an active admission path (Cosign verification was off-cluster only) — so this removal does not regress an already-active control, but does close off that specific implementation path. A native or alternative replacement for signature verification is not yet designed; tracked as future work, not blocking this ADR.

### Mentor rejection demo (re-run under fully-native stack, 22/07)

All 6 fixtures in `docs/evidence/mandate-05/native-rejection-demo/`, via `kubectl apply --dry-run=server`:

| Fixture | Denied by |
|---|---|
| `good-native-compliant-pod.yaml` | *(passes, as expected)* |
| `bad-latest-image-pod.yaml` | `ValidatingAdmissionPolicy` `mandate05-native-image-reference` |
| `bad-implicit-latest-pod.yaml` | `ValidatingAdmissionPolicy` `mandate05-native-image-reference` |
| `bad-first-party-tag-pod.yaml` | `ValidatingAdmissionPolicy` `mandate05-native-image-reference` |
| `bad-missing-resources-pod.yaml` | `ValidatingAdmissionPolicy` `mandate05-native-resource-requirements` |
| `bad-root-pod.yaml` | `PodSecurity "restricted:v1.35"` (`Error from server (Forbidden)`) |

No Kyverno involvement in any of the 6 outcomes — confirmed by re-running after the Audit downgrade (PR #339), where Kyverno could no longer have blocked anything even if it wanted to. Full command list and raw output: `docs/docx_cdo01/mandate05/karpenter-elastic-batch2-batch3-20260722.md`.

### Rollback (this update)

- PSA enforce rollback: revert PR #338 (drops back to `audit`/`warn=restricted`, no enforcement) — fastest, lowest-risk rollback if any workload regresses.
- Kyverno retirement rollback: revert PR #341 then #340 then #339 in that order (git revert, Argo recreates the app/policies from git automatically) — full Kyverno stack restorable within one Argo sync cycle if a real need for `verifyImages`/PolicyReport resurfaces before a native replacement exists.
- `otel-collector-agent` rollback: revert PR #337 (`enabled: true`) — DaemonSet redeploys immediately, no data was deleted.

### Exceptions — final disposition

- `m05-baseline-kafka-init-chown`: **closed**. In-cluster Kafka removed entirely (PR #324, Mandate #8 cleanup) — the workload this exception covered no longer exists.
- `m05-baseline-aiops-engine-runtime`: **still open, accepted risk**. PSA has no per-workload exception mechanism (unlike the retired Kyverno `preconditions`), so this is not a registerable exception in the same sense — it is a known, accepted gap: the already-running `aiops-engine` pod is unaffected, but its next recreate (crash restart, node drain, redeploy) will be rejected by admission until AIO02 hardens its `securityContext` or it is isolated to a differently-scoped namespace. See `docs/evidence/mandate-05/exception-register.yaml` for the updated entry.
