# Mandate 05 Native Runtime Hardening Migration Evidence

**Date:** 2026-07-21
**Cluster:** techx-corp-tf3
**Namespace:** techx-tf3
**Goal:** Replace Kyverno admission enforcement with Kubernetes-native controls without downtime, without gutting Kyverno's Cosign `verifyImages` capability (kept, see Status below).

**Status as of this commit: NOT YET LIVE-VERIFIED.** All checks below were run as `kubectl apply --dry-run=server` against the real API server (schema/CEL-compile validation only). The actual GitOps deploy (PR #291 → merge → Argo CD sync of `native-admission-policies` + `techx-infrastructure-app`) has **not happened yet** at the time this doc was written. Do not read any line below as a claim that native controls are already blocking production traffic — they are code-complete and dry-run-clean, not live-enforced yet.

## Native Controls — target state (this PR)

| Requirement | Native control | Enforcement state after this PR merges |
|---|---|---|
| No missing resource requests/limits | `ValidatingAdmissionPolicy` `mandate05-native-resource-requirements` + ResourceQuota | `Deny` |
| No `latest` or implicit latest images | `ValidatingAdmissionPolicy` `mandate05-native-image-reference` | `Deny` |
| First-party ECR image digest pinning | same policy, second validation | `Deny` |
| No root / no privileged runtime | Pod Security Admission `restricted` | **`audit`/`warn` only — `enforce` intentionally NOT set** (see Open Item below) |

Kyverno (`custom-baseline-security-context`, `disallow-latest-tag`, `require-first-party-image-digest`, `require-resource-requests`) **remains deployed and `Enforce`, unchanged, running in parallel.** It is not being removed by this PR — that is tracked separately as PM-172, which has not been given the go-ahead. Kyverno also continues to be the only mechanism capable of image-signature verification (`verifyImages`/Cosign, PM-114/127/128) once that is built; CEL/VAP has no equivalent.

## Open Item — PSA `enforce=restricted` deliberately not enabled

Native PSA `restricted` has no per-workload exception mechanism (unlike Kyverno's label-based `preconditions`). Two known exceptions from `docs/evidence/mandate-05/exception-register.yaml`:

- **`kafka` (`m05-baseline-kafka-init-chown`):** in-cluster Kafka is retired per Mandate #8 (Kafka → MSK migration, confirmed complete by CDO02); the workload no longer serves real traffic and is pending deletion. No remediation was attempted (fsGroup-based non-root chown was evaluated as technically plausible — `values-prod.yaml` already sets `podSecurityContext.fsGroup: 1000` for kafka — but not pursued since the workload is being decommissioned, not hardened).
- **`aiops-engine` (`m05-baseline-aiops-engine-runtime`):** confirmed to have **no manifest in this GitOps repository at all** — it is `kubectl apply`-managed directly by AIO02, outside ArgoCD. There is nothing in this repo for CDO01 to edit. AIO02 has not yet handed over a manifest to bring it under GitOps management. Deferred; owner will resolve separately.

Turning on `pod-security.kubernetes.io/enforce=restricted` today would admission-reject any recreate/restart of either workload while they are still running with root/privileged security contexts. Namespace stays at `audit`/`warn=restricted` only until this is revisited.

**Third, previously-unregistered violation found via live dry-run (2026-07-21):** testing `enforce=restricted` with `kubectl apply --dry-run=server` surfaced a warning that goes beyond the two known exceptions:

```
Warning: existing pods in namespace "techx-tf3" violate the new PodSecurity enforce level "restricted:v1.35"
Warning: aiops-engine-5d5c7964c6-pz569: allowPrivilegeEscalation != false, unrestricted capabilities, runAsNonRoot != true, seccompProfile
Warning: kafka-7cdc4476fb-9fww2: allowPrivilegeEscalation != false, unrestricted capabilities, runAsNonRoot != true, runAsUser=0
Warning: otel-collector-agent-49sm6 (and 3 other pods): hostPort, restricted volume types
```

The DaemonSet `otel-collector-agent` — the shared OpenTelemetry Collector running on every node, used by all 18 application services for trace/metric export — also violates `restricted`: 6 container ports declared with `hostPort` (`jaeger-compact` 6831/UDP, `jaeger-grpc` 14250, `jaeger-thrift` 14268, `otlp` 4317, `otlp-http` 4318, `zipkin` 9411, all forbidden under `restricted`) and a `hostPath` volume (`hostfs`, not in the `restricted` allowed-volume-types list). This is a cluster-wide DaemonSet, not a single deprecated/deferred workload — its blast radius on enforcement is larger than either registered exception (any node replacement, drain, or DaemonSet rollout would strand that node's collector pod in a permanent admission failure until remediated).

**Decision (2026-07-21, after seeing this live):** `enforce=restricted` stays off. This finding, not just the two registered exceptions, is now the primary reason. Remediating `otel-collector-agent` (moving off `hostPort`/`hostPath`, or an equivalent redesign) has not been scoped yet and is left open for follow-up.

## Rejection Demo Commands (dry-run, run before merge)

```bash
kubectl apply --dry-run=server -f gitops/policies/native/mandate-05-runtime-policy.yaml
kubectl apply --dry-run=server -f gitops/infrastructure/resource-quota.yaml
kubectl apply --dry-run=server -f gitops/infrastructure/namespace-techx-tf3.yaml
kubectl apply --dry-run=server -f docs/evidence/mandate-05/native-rejection-demo/good-native-compliant-pod.yaml
kubectl apply --dry-run=server -f docs/evidence/mandate-05/native-rejection-demo/bad-latest-image-pod.yaml
kubectl apply --dry-run=server -f docs/evidence/mandate-05/native-rejection-demo/bad-implicit-latest-pod.yaml
kubectl apply --dry-run=server -f docs/evidence/mandate-05/native-rejection-demo/bad-first-party-tag-pod.yaml
kubectl apply --dry-run=server -f docs/evidence/mandate-05/native-rejection-demo/bad-missing-resources-pod.yaml
```

## Dry-run Results Captured (2026-07-21, before merge)

- All 4 modified/created config files (`mandate-05-runtime-policy.yaml`, `limit-range.yaml`, `resource-quota.yaml`, `namespace-techx-tf3.yaml`) applied clean via `--dry-run=server` before merge — no CEL compile error, no schema error.
- The 5 demo manifests were dry-run **before the new VAP existed server-side**, so what actually blocked them was still Kyverno (still `Enforce`):
  - `bad-latest-image-pod.yaml`, `bad-implicit-latest-pod.yaml`, `bad-first-party-tag-pod.yaml` → denied by Kyverno `disallow-latest-tag` / `require-first-party-image-digest`.
  - `good-native-compliant-pod.yaml` → accepted, as expected.
  - `bad-missing-resources-pod.yaml` → **unexpectedly accepted** — root-caused to the *live* (pre-merge) `LimitRange` still having `default`/`defaultRequest`, which silently filled in resources before Kyverno's `require-resource-requests` rule could evaluate the pod. This was captured as live confirmation of the defaulting gap; post-merge verification later showed that merely leaving `min`/`max` in `LimitRange` was still not enough because Kubernetes materialized `default`/`defaultRequest` from `max`.

## Hotfix 2026-07-21 — remove LimitRange defaulting path

Post-merge verification of PR #291 showed `bad-missing-resources-pod.yaml` was still accepted. The live admission response included the `kubernetes.io/limit-ranger` annotation and filled the missing container resources as `requests.cpu=4`, `requests.memory=4Gi`, `limits.cpu=4`, and `limits.memory=4Gi`.

Root cause: a Container `LimitRange` with only `min`/`max` still causes the Kubernetes `LimitRanger` admission plugin to materialize `default` and `defaultRequest` from `max`. Because this mutation runs before validating admission, `mandate05-native-resource-requirements` sees an already-mutated Pod and cannot prove the workload author explicitly declared resources.

Hotfix decision: remove `gitops/infrastructure/limit-range.yaml` from GitOps and rely on:

- `ValidatingAdmissionPolicy` for per-Pod explicit `requests`/`limits`.
- `ResourceQuota` for namespace-level cost/capacity headroom (`requests.cpu=12`, `requests.memory=16Gi`, `limits.cpu=48`, `limits.memory=30Gi`, `pods=100`).

Required after this hotfix merges and Argo reconciles:

```bash
kubectl get limitrange -n techx-tf3
kubectl apply --dry-run=server -f docs/evidence/mandate-05/native-rejection-demo/bad-missing-resources-pod.yaml
```

Expected result: no `LimitRange` remains in `techx-tf3`, and `bad-missing-resources-pod.yaml` is denied by `mandate05-native-resource-requirements`.

**Required after merge, before this evidence doc or PM-170 can be considered actually verified:**
```bash
kubectl get applications -n argocd | grep -E "native-admission-policies|techx-infrastructure-app|techx-corp"
kubectl get validatingadmissionpolicy,validatingadmissionpolicybinding
kubectl get limitrange -n techx-tf3
kubectl get pods -n techx-tf3
curl -sS -o /dev/null -w 'status=%{http_code}\n' https://d2tn71186d7ilz.cloudfront.net/
# re-run the 5 dry-run commands above — this time the two native VAPs must be
# what denies the 4 bad manifests, not Kyverno (both mechanisms will agree,
# but the native one is now the one that matters for the mentor's "native"
# requirement)
```

## Production Health Gate (to run after merge)

```bash
kubectl get applications -n argocd
kubectl get deploy,statefulset,rollout -n techx-tf3
curl -sS -o /dev/null -w 'status=%{http_code} latency=%{time_total}\n' https://d2tn71186d7ilz.cloudfront.net/
curl -sS -o /dev/null -w 'status=%{http_code} latency=%{time_total}\n' https://d2tn71186d7ilz.cloudfront.net/api/products
```

## Kyverno Retirement — not in scope here

Kyverno controller and its 4 `ClusterPolicy` objects are **untouched** by this PR. Removing them is tracked as PM-172, which has not been approved to start. This migration's goal is to make native controls the authoritative enforcement path for the mentor's "no third-party admission tool" requirement; Kyverno keeps running in parallel for `verifyImages`/Cosign and background PolicyReport reconciliation, which native VAP/PSA cannot do.
