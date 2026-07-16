# ADR 0010: Mandate 5 runtime hardening and admission enforcement

**Status:** Accepted for controlled rollout
**Date:** 2026-07-16
**Owner:** CDO01 / TF3 Security
**Reviewer sign-off:** Pending TF3 platform owner and mentor

## Context

The TechX namespace contained runtime hardening gaps: incomplete security
contexts, tag-based image references, and policy rules that only audited
resources/security settings. Manual chart hygiene is insufficient because a
future deployment can omit a field and still reach the cluster.

Mandate 5 requires admission-time rejection of dangerous workloads without
breaking the public storefront or the protected flagd incident path.

## Decision

Kyverno is the admission guardrail for namespace `techx-tf3`. The policy set
is rolled out in this order: resources, baseline security context, latest-tag
prohibition, then first-party digest pinning. Each policy starts in Audit and
is promoted independently only after the listed entry gates are met.

| Policy | Enforced requirement | Intended scope |
| --- | --- | --- |
| `require-resource-requests` | CPU/memory requests and limits for application and init containers | All Pods in `techx-tf3` |
| `custom-baseline-security-context` | RuntimeDefault seccomp, non-root, APE=false, drop ALL, and no UID 0 | TechX workloads except approved infrastructure exceptions below |
| `disallow-latest-tag` | No explicit or implicit `latest`; all images have a fixed tag or digest | All Pods in `techx-tf3` |
| `require-first-party-image-digest` | TechX app images use the TF3 ECR sha256 digest | The 18 first-party TechX application labels |

The Helm chart merges security and resource defaults into component, sidecar,
and init-container manifests. Per-service values retain their production
sizing; defaults close omissions rather than replace explicit sizing.

PM-101 provides provenance before deployment: Trivy blocks HIGH/CRITICAL
findings before push and keyless GitHub OIDC Cosign signs the approved ECR
digest. Kyverno Cosign verification is deferred as an optional defence-in-depth
policy; digest pinning plus CI signing is the required closure scope.

## Approved baseline-context exceptions

These are exact label selectors, not namespace exclusions. They remain subject
to resource and latest-tag policies.

| Selector | Reason | Owner | Review / expiry | Removal condition |
| --- | --- | --- | --- | --- |
| `app.kubernetes.io/name=cloudflared` | Third-party tunnel image lacks an owned chart override in this repository. | Platform | 2026-07-30 | Upstream/chart values supply verified non-root context. |
| `app.kubernetes.io/name=flagd` | Protected incident-injection component; configuration and OpenFeature hooks must not be disrupted. | Platform | 2026-07-30 | Verified upstream values harden both flagd and init config copy. |
| `app.kubernetes.io/name=jaeger` | Third-party observability chart requires a compatibility validation. | Observability | 2026-07-30 | Jaeger chart values pass non-root startup test. |
| `app.kubernetes.io/name=opensearch` | Stateful search node needs data-path validation before context enforcement. | Observability | 2026-07-30 | PVC/write-path test passes with hardened values. |
| `app.kubernetes.io/name=opentelemetry-collector` | Host-metrics DaemonSet has host/agent compatibility requirements. | Observability | 2026-07-30 | Agent runs with documented least privilege. |
| `app.kubernetes.io/name=prometheus` | Third-party observability chart requires a compatibility validation. | Observability | 2026-07-30 | Prometheus chart values pass non-root startup test. |
| `app=aiops-engine` | Separate AIO-owned workload, currently root and not managed by this GitOps chart. | AIO owner | 2026-07-23 | AIO supplies a hardened manifest or the workload is removed. |

No first-party TechX application, including currency, llm, or product-reviews,
is exempt. PostgreSQL is hardened with UID/GID 999 and fsGroup 999; Kafka is
hardened with an UID 1000 init container and fsGroup 1000 instead of root
`chown`.

## Rollout and rollback

1. Render all production Helm values and run policy tests.
2. Merge Audit policies through GitOps and reconcile active controller reports,
   not stale ReplicaSet reports.
3. Promote one policy to Enforce, wait for ArgoCD Synced/Healthy and every
   workload rollout, then verify storefront HTTP 200 and no CrashLoopBackOff.
4. Demonstrate a rejected root, missing-resource, latest-image, and
   first-party-tag-only Pod with `kubectl apply --dry-run=server`.
5. Repeat for the next policy.

Rollback is a reviewed Git revert of the individual Enforce commit followed by
ArgoCD sync confirmation. Never edit a GitOps-managed ClusterPolicy directly
with `kubectl edit`. The flagd service, flag configuration, and OpenFeature
hooks are out of scope for this work and must remain unchanged.

## Acceptance evidence

- rendered production manifests show no latest/implicit-latest image and no
  UID 0;
- current active workload policy results have no unexplained failure;
- rejection output for every negative manifest in
  `docs/evidence/mandate-05/admission-tests/`;
- Argo application status, workload readiness, event snapshot, and storefront
  HTTP 200 evidence after every Enforce phase; and
- PM-101 Trivy/Cosign artifact plus a digest-to-running-workload mapping.

## Sign-off

| Role | Name | Signature / date |
| --- | --- | --- |
| Implementation owner | CDO01 / TF3 Security | Pending |
| Platform reviewer | TF3 Platform owner | Pending |
| Mentor | Assigned mentor | Pending |
