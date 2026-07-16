# Mandate 5 — controlled path to admission enforcement

**Status:** execution plan; this document does not switch any policy to Enforce.

**Date:** 2026-07-16
**Target namespace:** techx-tf3
**Change owner:** CDO01 / TF3 Security
**Required reviewers:** TF3 platform owner and mentor

## 1. Closure objective

Close Mandate 5 without an availability regression. A configuration that violates
a required runtime rule must be rejected by Kyverno during admission, while the
currently running TechX application workload remains healthy.

The enforced application controls are:

1. every application and init container has CPU and memory requests and limits;
2. containers cannot run as root, cannot escalate privilege, drop ALL Linux
   capabilities, and use RuntimeDefault seccomp;
3. images cannot use latest (including an implicit latest); first-party TechX
   ECR images must use a digest; and
4. the existing PM-101 build gate rejects HIGH/CRITICAL vulnerabilities and
   signs every pushed first-party digest with keyless Cosign.

readOnlyRootFilesystem remains a workload-by-workload hardening control. It is
enabled where write-path testing is successful, but is not made a global
admission requirement until all application and stateful write paths are
verified.

## 2. Current facts and planning constraints

The following were observed on 2026-07-16 and must be refreshed immediately
before each cutover phase:

| Observation | Consequence |
| --- | --- |
| Kyverno policies are currently Audit. | No existing workload should be blocked until the pre-flight gates below pass. |
| The raw PolicyReport result contains 131 failures, including autogen results scoped to old Deployment/ReplicaSet revisions. | A raw Fail = 0 count is not a valid cutover gate. Reconcile active workload UIDs and templates first. |
| Current non-Job Pods had no container missing CPU/memory request or limit in the live check. | Do not add arbitrary resource values only to make a historical report green; fix rendered controller templates so the next rollout is compliant. |
| The chart template renders resources from .resources; it does not fall back to default.resources. | Adding only default.resources to values.yaml is ineffective. Change the template fallback or define complete resources for every component. |
| The chart still contains busybox:latest init containers. | A latest policy will reject future rollouts until those references are pinned. |
| Current OTel Pods have app.kubernetes.io/name=opentelemetry-collector. | Do not use otel-collector as an exception selector; it will not match. |

Retain the PolicyReport as audit evidence, but stale reports must not be used to
declare active Pods non-compliant or to justify a broad policy exemption.

## 3. Scope and exception decision

### 3.1 First-party workloads

All 18 TechX application workloads in techx-tf3 are in scope for every control
in this plan. They receive no permanent exception for root, capabilities,
seccomp, resources, or image pinning.

### 3.2 External infrastructure

An exception is acceptable only for a third-party/operational component which
cannot safely receive the required security context through its upstream chart
in this release. It is an exception to **baseline security context only**; it
is not an exception to resource requirements or the latest prohibition.

Use exact app.kubernetes.io/name selectors and keep the list minimal:

| Candidate label value | Reason to assess | Decision required before enforce |
| --- | --- | --- |
| flagd | Incident-injection control plane; it must not be disabled. | Exception only if upstream security context cannot be applied safely; document owner and re-test date. |
| jaeger | Third-party observability workload. | Prefer chart-level hardening; otherwise time-boxed baseline exception. |
| opensearch | Stateful third-party workload. | Validate data/write paths before any change; time-boxed exception only if needed. |
| prometheus | Third-party observability workload. | Prefer values override; exception only for verified incompatibility. |
| opentelemetry-collector | DaemonSet with observed baseline failures. | Validate host/agent requirements; do not use the incorrect otel-collector label. |
| cloudflared | Operational tunnel component. | Add only if a current violation is demonstrated. |

aiops-engine is **not** automatically infrastructure. Its current violation must
be remediated as an application workload or receive a separately approved,
time-bounded exception with an owner. Grafana is likewise not added merely by
category; an exception requires an observed current violation.

Every approved exception must appear in the ADR with policy/rule, selector,
reason, owner, expiry/review date, and rollback/remediation action. Never
exclude the entire techx-tf3, monitoring, or kube-system namespace beyond the
platform namespaces already intentionally outside this policy scope.

## 4. Required implementation changes

### Phase A — establish a renderable compliant baseline

1. In phase3 - information/techx-corp-chart/templates/_objects.tpl, make
   component resources fall back to a complete default.resources value, or set
   complete per-component resources. The selected default must contain
   requests.cpu, requests.memory, limits.cpu, and limits.memory.
2. Put production-sized values in phase3 - information/deploy/values-prod.yaml;
   do not use an arbitrary common default to hide a sizing decision. Preserve
   specialized values for stateful and observability components.
3. Apply the baseline securityContext and pod seccompProfile to every
   first-party component, including init containers. A compliant first-party
   container has:

   ~~~yaml
   securityContext:
     runAsNonRoot: true
     allowPrivilegeEscalation: false
     capabilities:
       drop: ["ALL"]
   ~~~

   and the Pod has:

   ~~~yaml
   securityContext:
     seccompProfile:
       type: RuntimeDefault
   ~~~

   runAsUser: 0 is prohibited at pod and container level. Numeric non-root
   UID/GID must be set where an image does not declare a safe USER.
4. Pin all busybox:latest and any other implicit/latest image reference to an
   approved immutable digest. First-party ECR image references in production
   values must use repository@sha256:<digest>.
5. Do not alter flagd configuration, OpenFeature hooks, or incident injection
   behavior while making these changes.

### Phase B — complete and scope Kyverno rules

Update the existing policies under gitops/policies/kyverno while they remain
in Audit:

| Policy | Required rules |
| --- | --- |
| require-resource-requests.yaml | Require CPU and memory requests/limits for containers, initContainers, and ephemeralContainers when present. Keep only platform namespace exclusions. |
| baseline-security-context.yaml | Retain APE=false, drop ALL, and RuntimeDefault; add runAsNonRoot: true and a deny rule for UID 0. Apply rules to init containers as well. Add only approved exact-label infra exceptions. |
| disallow-latest-tag.yaml (new) | Reject explicit latest and an image with no tag/digest; cover ordinary, init, and ephemeral containers. |
| require-first-party-image-digest.yaml (new) | For 197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp/*, require @sha256:<64 hex>. This is stronger than allowing an arbitrary non-latest tag. |

Keep third-party images out of the first-party digest rule but require that they
are fixed version tags or approved digests and never latest. Do not make a
Cosign admission policy a closure dependency: it is optional defence in depth.
PM-101 CI signing and verification evidence remains mandatory.

### Phase C — produce PM-101 release evidence

1. Trigger the build workflow from main after the policy-compatible image
   changes land.
2. Require a successful pre-push Trivy gate at HIGH=0 and CRITICAL=0 for every
   first-party build target.
3. Retain the per-image Trivy JSON artifact even if the gate fails.
4. Verify a keyless GitHub OIDC Cosign signature immediately after each ECR
   push. Record digest, certificate identity, Git SHA, workflow run URL/ID,
   Trivy artifact, and Cosign verification output in the evidence matrix.
5. Run and retain the non-blocking periodic scan for external images. Its
   exception list must name image, owner, current fixed tag/digest, scan date,
   and remediation/upgrade decision.

## 5. Audit-to-enforce cutover

Do not switch all policies in one commit. Each phase is an independently
reviewable GitOps change and has a rollback commit prepared before sync.

| Order | Change | Entry gate | Exit gate |
| ---: | --- | --- | --- |
| 0 | Reconcile reports and render production chart | Current active templates identified; exceptions approved. | No unexplained violation in the rendered first-party workload set. |
| 1 | Enforce resource requirements | All active workload templates have four resource fields, including init containers. | Argo sync Healthy; all Deployments/StatefulSets/DaemonSets rollout successfully. |
| 2 | Enforce baseline security context | First-party workload render is compliant; only ADR-approved infra exceptions remain. | No CrashLoopBackOff; storefront smoke test remains successful. |
| 3 | Enforce latest/digest policies | Every rendered image passes policy; ECR digests exist. | A compliant image bump can be admitted and deployed. |
| 4 | Close PM-101 evidence | Full main workflow green and ECR signature verification complete. | Running first-party digests map one-to-one to scan/signature evidence. |

For each policy, change only that policy's validationFailureAction from Audit to
Enforce; do not combine the change with unrelated application features. ArgoCD
performs the policy sync. The rollback is a reviewed Git revert of that one
policy change, followed by confirmation that ArgoCD has synced; do not use
imperative kubectl edit on a GitOps-managed policy.

## 6. Pre-flight and verification procedure

### 6.1 Render and policy pre-flight

~~~bash
helm template techx-corp "phase3 - information/techx-corp-chart" \
  -f "phase3 - information/techx-corp-chart/values.yaml" \
  -f "phase3 - information/deploy/values-prod.yaml" \
  > /tmp/techx-prod-rendered.yaml

rg -n 'image:|runAsNonRoot:|allowPrivilegeEscalation:|seccompProfile:|resources:' \
  /tmp/techx-prod-rendered.yaml
~~~

Use Kyverno CLI policy tests or server-side dry-run against a non-production
copy of the rendered manifests before the Argo sync. A good manifest must be
admitted under each proposed Enforce rule.

### 6.2 Admission rejection demonstration

Create test manifests in a temporary local directory only. Apply them to
techx-tf3 with --dry-run=server after the relevant policy is Enforced. Each
command must fail and show the Kyverno policy/rule in the denial message:

~~~bash
kubectl -n techx-tf3 apply --dry-run=server -f test-missing-resources.yaml
kubectl -n techx-tf3 apply --dry-run=server -f test-root.yaml
kubectl -n techx-tf3 apply --dry-run=server -f test-latest-image.yaml
kubectl -n techx-tf3 apply --dry-run=server -f test-first-party-tag-not-digest.yaml
~~~

The four test manifests respectively omit resources, request UID 0/miss
runAsNonRoot, use latest, and use a first-party tag without a digest. Keep the
command output and a matching compliant-manifest success output as mentor
evidence. No rejected test Pod should need cleanup because it was never created.

### 6.3 Runtime and report verification

~~~bash
kubectl -n techx-tf3 get deploy,statefulset,daemonset
kubectl -n techx-tf3 get pods
kubectl -n techx-tf3 get events --sort-by=.lastTimestamp
kubectl -n techx-tf3 get policyreport -o yaml
~~~

Reconcile PolicyReport scopes with the active controller revision and Pod UID;
do not fail a phase merely because an old ReplicaSet record remains. The final
report must show zero **unexplained active** failures. Confirm the public
storefront returns HTTP 200 and that no critical pod has CrashLoopBackOff,
ImagePullBackOff, or an unready rollout.

## 7. Required evidence and ADR

Create docs/adr/0010-mandate-05-runtime-hardening.md before the first Enforce
commit. It must include:

- the policy/rule matrix and enforcement scope;
- exception selector, reason, owner, expiry/review date, and removal plan;
- why first-party ECR digests are required and how PM-101 keyless signing
  establishes provenance;
- audit observation period and exact gates for every Audit-to-Enforce step;
- SLO, storefront, flagd, and rollback safeguards; and
- implementation owner and reviewer sign-off.

The final evidence pack must contain:

1. before/after active-workload policy-report reconciliation;
2. rendered-manifest compliance results;
3. Argo sync and rollout status for each Enforce phase;
4. rejection output for all four violating test manifests plus one compliant
   manifest acceptance;
5. storefront smoke result and pod health snapshot; and
6. PM-101 per-digest Trivy/Cosign evidence and the external-image scan report.

## 8. Mandate 5 closure checklist

- [ ] All first-party application and init containers have explicit CPU/memory
  requests and limits.
- [ ] All first-party application and init containers are non-root, cannot
  escalate privilege, drop ALL capabilities, and use RuntimeDefault seccomp.
- [ ] Every approved infrastructure exception is exact-scoped, owned, and
  time-bounded in ADR 0010.
- [ ] No image is latest or implicit latest; all first-party ECR production
  references are digest pinned.
- [ ] Resource, baseline, latest, and first-party digest policies are Enforced
  in the intended scope.
- [ ] A root, missing-resource, latest-image, and non-digest first-party
  manifest are rejected by admission.
- [ ] Active workloads are healthy and the storefront remains reachable.
- [ ] PM-101 has a green main run, Trivy reports, verified Cosign signatures,
  and a live-digest evidence mapping.
- [ ] ADR 0010 and the complete evidence pack are committed and signed off.
