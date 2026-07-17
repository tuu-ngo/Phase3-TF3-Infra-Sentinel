# Mandate 5 — Runtime hardening completion plan

**Date:** 2026-07-16

**Deadline:** 2026-07-17

**Working branch:** `mandate-5/integration`

**Scope:** PM-92 Pod Security, PM-95 image immutability/digest pinning,
PM-101 Trivy/Cosign, Kyverno admission enforcement, mentor acceptance evidence

**Constraints:** no additional fixed infrastructure cost, no storefront SLO
regression, operations endpoints remain private, and flagd/fault injection must
not be disabled or bypassed

## 1. Executive status

The Jira task split is directionally correct, but the combined work is not yet
sufficient to close Mandate 5. PM-92, PM-101 and the Kyverno audit task cover
the main implementation areas; the mandate additionally requires production
remediation, admission enforcement, a real rejection demonstration and a
signed end-to-end decision/evidence record.

Strict progress against the three Jira DoD lists is currently:

| Work item | Passed DoD | Progress | Main remaining gap |
| --- | ---: | ---: | --- |
| PM-92 Pod Security | 3/4 | 75% | Baseline coverage is below 80%. |
| Kyverno audit policies | 4/5 | 80% | PolicyReport no longer matches the original evidence snapshot. |
| PM-101 Trivy/Cosign | 1/4 | 25% | No real workflow run, scan artifact or ECR signature yet. |
| **Combined Jira DoD** | **8/13** | **61.5%** | Implementation exists, production acceptance does not. |

This percentage is planning progress, not a completion claim. Mandate 5 remains
open until both final acceptance conditions are demonstrated:

1. a violating manifest is rejected by admission; and
2. the running cluster has no unexplained violation of an enforced rule.

## 2. Verified live baseline

Snapshot collected on 2026-07-16 against the production cluster and ECR:

| Control | Current result | Target before closure |
| --- | ---: | ---: |
| PSA labels | `audit=baseline`, `warn=baseline`, no `enforce` | Preserve during remediation; enforce only after clean audit. |
| Kyverno controllers | 4/4 deployments available | 4/4 available throughout cutover. |
| Kyverno policies | 2 Ready policies, both `Audit` | Required policies switched to `Enforce` in controlled order. |
| Baseline context: APE=false + drop ALL + seccomp | 10/32 containers | 32/32, or a signed, time-bounded exception. |
| `runAsNonRoot` | 14/32 containers | All first-party app containers; no unexplained root workload. |
| `readOnlyRootFilesystem` | 4/32 containers | Enable where write-path testing proves it safe; document stateful exceptions. |
| Explicit CPU/memory requests and limits | 31/32 workload containers | 32/32; OTel Collector is the current missing template. |
| Digest-pinned images | 18/32 containers | 32/32 running refs pinned by digest. |
| Floating, non-`latest` image refs | 14/32 containers | 0. Fixed tags are still mutable references. |
| ECR Cosign signatures | 0 | Every agreed first-party application digest signed and verified. |
| PM-101 Actions runs/artifacts | 0 | Full green run plus retained Trivy/Cosign artifacts. |
| PolicyReport aggregate | 267 reports, 441 pass, 180 fail | Current-resource report has zero unexplained failures. |
| Storefront smoke test | HTTP 200 | HTTP 200 before, during and after enforce. |

The PolicyReport aggregate contains historical ReplicaSet results. It must not
be presented as a current workload count without reconciling the report scope,
UID and active controller revision.

## 3. Branch and merge safety

`mandate-5/integration` currently contains:

- PM-92/non-root work from `e7c10a9`;
- the earlier PM-101 implementation from `d80df4e` plus `d86f5c8`; and
- the current `origin/main` baseline at the time the integration branch was
  assembled.

PM-101 has since been isolated and completed on
`feat/pm-101-trivy-cosign-gate` in PR #148. Therefore:

1. do not merge this integration branch directly into `main` before PR #148 is
   reviewed;
2. merge the isolated PM-101 PR first;
3. carry PM-92 through its own focused PR or reconcile it after rebasing the
   integration branch on the new `main`;
4. drop or resolve the duplicated older PM-101 commits during reconciliation;
5. keep the Audit-to-Enforce policy change in a separate final PR so rollback
   does not revert unrelated image or Dockerfile fixes.

This plan document does not authorize a production merge by itself.

## 4. Missing work beyond the existing Jira descriptions

### 4.1 Complete runtime remediation

- Apply the baseline context to every remaining first-party app:
  `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`, and
  `seccompProfile.type: RuntimeDefault`.
- Make the remaining first-party images run as a numeric non-root user and set
  `runAsNonRoot: true` in the workload template.
- Test application write paths before enabling `readOnlyRootFilesystem`.
- For PostgreSQL, Kafka, Valkey, OpenSearch and observability workloads, record
  required writable paths and provide `emptyDir`/PVC mounts where appropriate.
- Remove the broad `currency`, `llm`, and `product-reviews` policy exclusion
  after their images are fixed. A temporary root exception must not silently
  exempt APE, capability and seccomp controls that the image can already use.
- Add explicit resources to OTel Collector and verify every application,
  sidecar, init container and daemon container has CPU/memory requests and
  limits in Git, rather than relying only on LimitRange defaults.

### 4.2 Complete image immutability at runtime

- Replace all 14 remaining tag-only workload references with exact digests.
- Include Kafka, AIOps Engine, Cloudflared, Flagd, Grafana and its sidecars,
  Jaeger, PostgreSQL, Prometheus, Valkey, OpenSearch and OTel Collector.
- Reconcile the external-image scan list with the images actually running. A
  scan of an inventory digest is not evidence for a different live tag.
- Add admission policies which reject `:latest` and reject any image reference
  without `@sha256:`. PM-95 GitOps pinning alone does not prevent a later
  manifest from reintroducing a mutable tag.

### 4.3 Complete PM-101 production evidence

- Merge PR #148 to `main`.
- Manually dispatch the full build workflow because the workflow path filter
  will not run solely from CI/docs changes.
- Remediate every HIGH/CRITICAL finding until the agreed full service set is
  green.
- Confirm and document whether the official DoD set is 18 application services
  or the 20 current `ALL_SERVICES` build targets. The workflow may cover the
  superset, but the evidence table must identify the official 18 explicitly.
- Verify that each pushed digest has a keyless GitHub OIDC Cosign signature and
  successful `cosign verify` result.
- Retain `trivy-app-images-<run-id>` and
  `signed-release-evidence-<run-id>` artifacts.
- Map every first-party digest running in the cluster to the Git SHA, Actions
  run, Trivy report and Cosign verification report.
- Run the external-image workflow at least once and retain its artifact.

Residual evidence risk: the current workflow scans a local `linux/amd64`
candidate and subsequently rebuilds the multi-platform image for push. The ADR
must record that limitation, or the release flow must produce stronger proof
that the signed pushed digest corresponds to the scanned build output.

### 4.4 Extend Kyverno coverage

The final policy set for namespace `techx-tf3` must cover:

1. explicit CPU/memory requests and limits;
2. `allowPrivilegeEscalation: false`;
3. `capabilities.drop` containing `ALL`;
4. `seccompProfile.type: RuntimeDefault`;
5. `runAsNonRoot: true` for first-party workloads;
6. no `latest` tag;
7. digest-pinned image references; and
8. optionally, Cosign `verifyImages` for first-party ECR digests after PM-101
   has produced the signed inventory.

Rules must evaluate `containers`, `initContainers` and `ephemeralContainers`.
They must be scoped deliberately so a TF3 mandate does not unexpectedly block
unrelated namespaces. Exceptions must identify an owner, reason, exact workload
and expiry/review date.

Cosign admission verification is not required to close the original PM-101
DoD, but it is the recommended final authenticity control. External images must
use exact digest exceptions; an unrestricted external-registry bypass is not
acceptable.

## 5. Controlled execution phases

### Phase 0 — Freeze and reconcile evidence

Actions:

- Record current `main`, integration, PM-92 and PM-101 commit SHAs.
- Export the current workloads, image references, Kyverno policies and
  PolicyReports.
- Separate current Pod/controller results from historical ReplicaSet reports.
- Confirm the 18-service PM-101 inventory with the team.

Exit gate:

- one authoritative inventory exists for workloads, containers, images,
  exceptions and owners;
- the integration branch has no unknown or unrelated diff; and
- the merge order in section 3 is accepted by reviewers.

### Phase 1 — Remediate without enforcement

Actions:

- merge and roll out runtime securityContext/Dockerfile fixes in small batches;
- add missing resources;
- pin every live image to a digest;
- leave Kyverno in Audit while each batch rolls out;
- smoke-test storefront, checkout flow and flagd after every batch.

Exit gate:

- zero current, unexplained Audit failures for resources, APE, capabilities,
  seccomp, non-root and digest pinning;
- no critical workload in CrashLoopBackOff;
- ArgoCD Synced/Healthy; and
- storefront returns HTTP 200.

### Phase 2 — Produce scan and signature evidence

Actions:

- merge PM-101;
- run the full first-party workflow;
- remediate vulnerabilities;
- verify ECR signatures and artifacts;
- run the external-image review; and
- prepare the live-digest evidence matrix.

Exit gate:

- every agreed first-party image has a clean Trivy report and successful Cosign
  verification;
- no required digest is missing evidence; and
- external exceptions are explicit and match the live digest inventory.

### Phase 3 — Audit the complete policy set

Actions:

- deploy the additional policies in Audit;
- exercise normal ArgoCD sync and at least one legitimate rollout;
- run server-side dry-run negative manifests to confirm each policy matches the
  intended field; and
- review every failure with the workload owner.

Exit gate:

- two normal deployment/sync cycles produce no false positive;
- current PolicyReport has zero unexplained failure;
- all exceptions are signed and time-bounded; and
- rollback commits are prepared.

### Phase 4 — Switch Audit to Enforce

Enable one control at a time in this order:

```text
resources
  -> baseline securityContext
  -> runAsNonRoot
  -> disallow latest / require digest
  -> Cosign verifyImages (optional final step)
```

For each step:

1. merge only that policy action change;
2. wait for ArgoCD Synced/Healthy;
3. perform a legitimate deployment dry-run;
4. apply the corresponding invalid test manifest and confirm rejection;
5. check workload readiness, storefront and flagd; and
6. continue only if there is no unintended rejection or SLO impact.

Exit gate:

- required policies show `Enforce` and `Ready=True`;
- valid GitOps sync remains successful; and
- invalid manifests are denied by the admission webhook.

### Phase 5 — Mentor acceptance and closeout

Prepare three minimal negative manifests:

- `bad-root.yaml`: root-capable container or missing required runtime context;
- `bad-latest-image.yaml`: mutable/latest image reference; and
- `bad-missing-resources.yaml`: missing requests/limits.

The mentor must run real `kubectl apply` commands and see all three rejected.
After the demo, show:

- Kyverno controllers Running;
- enforced policies Ready;
- current PolicyReport with no unexplained violation;
- live digest inventory and PM-101 scan/signature mapping;
- ArgoCD Synced/Healthy;
- storefront HTTP 200;
- private operations paths still private; and
- flagd/fault injection unchanged and operational.

## 6. Rollback plan

Rollback is policy-specific and does not disable Kyverno globally:

1. change only the failing policy from `Enforce` back to `Audit` through Git;
2. let ArgoCD self-heal to the reviewed Audit version;
3. revert the most recent workload batch if it caused readiness/SLO regression;
4. retain PolicyReport and rejection output for incident analysis;
5. do not disable admission webhooks, remove flagd, expose private operations
   endpoints or weaken unrelated controls; and
6. record any temporary exception with owner, reason and expiry before retrying
   enforcement.

PM-101 rollback reverts the workflow merge; it does not delete existing ECR
signatures or change deployed digests. Digest-pinning rollback selects a
previous known-good signed digest, never a mutable tag.

## 7. Required evidence pack

Create or update the following before closure:

- signed Mandate 5 ADR covering all Audit/Enforce decisions;
- before/after workload compliance matrix;
- current PolicyReport export and summarized violation table;
- PM-101 first-party digest/scan/signature matrix;
- external-image exception and scan table;
- terminal output for each admission denial;
- ArgoCD/Kyverno health snapshot;
- storefront and critical-flow smoke-test output; and
- rollback commands and the exact commits used for cutover.

The final ADR must state:

- which policies are enforced;
- which policy, if any, remains in Audit and why;
- every active exception, owner and expiry;
- the Audit-to-Enforce cutover criteria;
- known residual risk, including the pre-push amd64 versus multi-platform build
  relationship; and
- implementation owner and reviewer signatures.

## 8. Suggested Jira subtasks

- `M5-01 — Remediate remaining runtime security violations`
- `M5-02 — Require digest and disallow floating tags at admission`
- `M5-03 — Produce PM-101 CI/ECR scan and signature evidence`
- `M5-04 — Reconcile PolicyReports and remove stale/invalid exceptions`
- `M5-05 — Kyverno Audit-to-Enforce cutover`
- `M5-06 — Admission rejection demo and signed Mandate 5 ADR`

## 9. Definition of complete

- [ ] No unexplained workload runs as root.
- [ ] Every container type has explicit CPU/memory requests and limits.
- [ ] Every runtime image is pinned by digest; no `latest` or tag-only ref.
- [ ] Every agreed first-party app image has current Trivy and Cosign evidence.
- [ ] External images have exact-digest exceptions and current scan evidence.
- [ ] Required Kyverno policies are Enforce and Ready.
- [ ] Current PolicyReport has zero unexplained violation.
- [ ] Mentor applies root/latest/missing-resources manifests and sees admission
      rejection.
- [ ] ArgoCD remains Synced/Healthy and no critical workload is CrashLooping.
- [ ] Storefront remains HTTP 200 and SLO is not degraded.
- [ ] Operations endpoints remain private.
- [ ] Flagd and fault-injection paths are unchanged.
- [ ] Signed ADR, evidence pack and rollback plan are committed.

Until every item above is complete, the TF must report Mandate 5 as in progress,
not complete.
