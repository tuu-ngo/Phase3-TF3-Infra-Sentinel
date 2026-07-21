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

## Otel PSA Migration PR1 — gateway added, no traffic moved

Branch `fix/mandate05-otel-gateway` starts the Otel PSA migration by adding a new `otel-gateway` Deployment/Service/ConfigMap and PDB. It does **not** change `OTEL_COLLECTOR_NAME`; rendered application workloads still point to `otel-collector`, so this PR does not move application telemetry traffic.

Rendered checks:

```text
ConfigMap otel-gateway 1
Deployment otel-gateway 1
Service otel-gateway 1
replicas 2
maxUnavailable 0
maxSurge 1
hostPorts []
hostPaths []
runAsNonRoot True
allowPrivilegeEscalation False
drop ['ALL']
seccomp RuntimeDefault
```

Server-side dry-run, with the EKS API reached through the SSM tunnel:

```text
configmap/otel-gateway created (server dry run)
service/otel-gateway created (server dry run)
deployment.apps/otel-gateway created (server dry run)
poddisruptionbudget.policy/otel-gateway-pdb created (server dry run)
networkpolicy.networking.k8s.io/prometheus-access configured (server dry run)
networkpolicy.networking.k8s.io/opensearch-access configured (server dry run)
```

Local verification:

```text
helm lint phase3 - information/techx-corp-chart ...: 1 chart(s) linted, 0 chart(s) failed
python3 -m pytest scripts/ci/test_runtime_hardening.py -q: 5 passed
python3 -m pytest scripts/ci/test_production_access_contract.py -q: 9 passed
git diff --check: clean
```

Quota headroom from the live snapshot at `2026-07-21T16:39:23+07:00` remains sufficient for two gateway replicas. Current quota use is `requests.cpu=3750m/12`, `requests.memory=7896Mi/16Gi`, `limits.cpu=16900m/48`, and `limits.memory=17523Mi/30Gi`; PR1 adds only `requests.cpu=200m`, `requests.memory=512Mi`, `limits.cpu=1000m`, and `limits.memory=1536Mi`.

## Otel PSA Migration PR2 — app telemetry endpoint switch

Branch `fix/mandate05-otel-switch` changes only the default application collector name:

```yaml
default:
  env:
    - name: OTEL_COLLECTOR_NAME
      value: otel-gateway
```

All application `OTEL_EXPORTER_OTLP_ENDPOINT` / `OTEL_COLLECTOR_HOST` values continue to use `$(OTEL_COLLECTOR_NAME)`, so rendered application telemetry clients move from `otel-collector` to `otel-gateway` without changing per-service code.

Safety dependency: live snapshot `2026-07-21T16:47:51+07:00` showed `origin/main=3e2114e` but Argo `techx-corp` was still live at `fb4a59e`; `otel-gateway` was therefore not live-verified yet. This PR must not be merged/deployed until PR1 has reconciled and these checks pass:

```bash
kubectl get application techx-corp -n argocd -o jsonpath='{.status.sync.revision}{" sync="}{.status.sync.status}{" health="}{.status.health.status}{"\n"}'
kubectl get deploy,svc,endpointslice,pdb -n techx-tf3 -l app.kubernetes.io/name=otel-gateway -o wide
kubectl get pods -n techx-tf3 -l app.kubernetes.io/name=otel-gateway -o wide
```

Expected before PR2 merge/deploy:

```text
techx-corp revision is at or after 3e2114e, Synced, Healthy
deployment/otel-gateway READY 2/2
otel-gateway Service and EndpointSlice have ready endpoints
otel-gateway-pdb exists
```

Local verification for PR2:

```text
helm lint phase3 - information/techx-corp-chart ...: 1 chart(s) linted, 0 chart(s) failed
helm template with Argo values: pass
render assertion: app OTEL_COLLECTOR_NAME values all resolve to otel-gateway; old otel-collector-agent still renders; otel-gateway still has no hostPort/hostPath
python3 -m pytest scripts/ci/test_runtime_hardening.py -q: 5 passed
python3 -m pytest scripts/ci/test_production_access_contract.py -q: 9 passed
git diff --check: clean
```

Server-side dry-run for 29 rendered workload objects passed. Kubernetes emitted the known PSA warning for the existing old `otel-collector-agent` (`hostPort` + `hostPath`), which remains the PR3/PR4 blocker; all app workload templates with `OTEL_COLLECTOR_NAME=otel-gateway` were accepted by admission in server dry-run.

## Otel PSA Migration PR3 — dedicated host metrics node-agent

Branch `fix/mandate05-otel-node-agent` adds a second OpenTelemetry Collector
subchart instance named `otel-node-agent`. This PR is additive: application
telemetry remains pointed at `otel-gateway`, and the old `otel-collector-agent`
DaemonSet remains deployed as a fallback.

What this PR introduces:

- `observability-system` namespace with PSA `audit`/`warn=baseline`.
- `otel-node-agent` DaemonSet rendered into `observability-system`.
- Host/kubelet metrics only: `hostmetrics` and `kubeletstats` receivers, no
  OTLP/Jaeger/Zipkin receiver ports for application traffic.
- Prometheus ingress allow-rule from
  `observability-system/app.kubernetes.io/name=otel-node-agent` to port 9090.
- Production resources of `requests.cpu=10m`, `requests.memory=128Mi`,
  `limits.cpu=250m`, and `limits.memory=256Mi` per scheduled node.

Expected rendered properties before merge:

```text
DaemonSet otel-node-agent exactly 1
namespace observability-system
hostPorts []
hostPath / readOnly true
runAsNonRoot true
allowPrivilegeEscalation false
capabilities.drop ["ALL"]
seccomp RuntimeDefault
updateStrategy RollingUpdate maxUnavailable=0 maxSurge=1
application OTEL_COLLECTOR_NAME remains otel-gateway
old otel-collector-agent still renders
```

Local render assertions captured before PR:

```text
DaemonSet otel-node-agent namespace observability-system
hostPorts []
hostPaths [{'name': 'hostfs', 'hostPath': {'path': '/'}}]
hostfsMounts [{'name': 'hostfs', 'mountPath': '/hostfs', 'readOnly': True, 'mountPropagation': 'HostToContainer'}]
securityContext {'allowPrivilegeEscalation': False, 'capabilities': {'drop': ['ALL']}, 'runAsGroup': 10001, 'runAsNonRoot': True, 'runAsUser': 10001, 'seccompProfile': {'type': 'RuntimeDefault'}}
updateStrategy {'rollingUpdate': {'maxSurge': 1, 'maxUnavailable': 0}, 'type': 'RollingUpdate'}
oldCollectorRendered 1
appCollectorNameMismatch []
nodeAgentReceivers ['hostmetrics', 'kubeletstats']
metricsPipeline {'exporters': ['otlphttp/prometheus'], 'processors': ['k8sattributes', 'memory_limiter', 'resourcedetection', 'resource', 'batch'], 'receivers': ['hostmetrics', 'kubeletstats']}
prometheusExporterEndpoint http://prometheus.techx-tf3.svc.cluster.local:9090/api/v1/otlp
networkPolicyAllowsNodeAgent True
observabilityNamespacePSA {'pod-security.kubernetes.io/audit': 'baseline', 'pod-security.kubernetes.io/audit-version': 'v1.35', 'pod-security.kubernetes.io/warn': 'baseline', 'pod-security.kubernetes.io/warn-version': 'v1.35'}
```

Server-side dry-run captured before PR:

```text
namespace/observability-system created (server dry run)
networkpolicy.networking.k8s.io/prometheus-access configured (server dry run)
serviceaccount/otel-node-agent created (server dry run)
configmap/otel-node-agent created (server dry run)
clusterrole.rbac.authorization.k8s.io/otel-node-agent created (server dry run)
clusterrolebinding.rbac.authorization.k8s.io/otel-node-agent created (server dry run)
Warning: would violate PodSecurity "restricted:v1.35": restricted volume types (volume "hostfs" uses restricted volume type "hostPath")
daemonset.apps/otel-node-agent created (server dry run)
```

Note: the node-agent server dry-run used a temporary rendered manifest with
namespace changed from `observability-system` to existing namespace `techx-tf3`,
because Kubernetes server dry-run does not persist the new namespace for later
objects in the same PR. The exact `observability-system` namespace manifest
itself dry-ran clean, and the local Helm render verifies the final node-agent
namespace is `observability-system`.

Local verification:

```text
helm lint phase3 - information/techx-corp-chart ...: 1 chart(s) linted, 0 chart(s) failed
helm template with Argo values: pass
python3 -m pytest scripts/ci/test_runtime_hardening.py -q: 5 passed
python3 -m pytest scripts/ci/test_production_access_contract.py -q: 9 passed
git diff --check: clean
```

Post-merge scheduling hotfix:

```text
Observed after PR3 merge: otel-node-agent was created but one DaemonSet pod
remained Pending on ip-10-0-26-153 because that node had 1915m/1930m CPU
requests allocated. The original node-agent request of 50m could not fit even
though actual CPU usage was low. Reduce the node-agent CPU request to 10m while
keeping the 250m limit so the collector can still burst without blocking
DaemonSet coverage on tightly packed nodes.
```

Required after this PR merges and Argo reconciles:

```bash
kubectl get ns observability-system --show-labels
kubectl get ds,pods -n observability-system -l app.kubernetes.io/name=otel-node-agent -o wide
kubectl get networkpolicy prometheus-access -n techx-tf3 -o yaml
kubectl get application techx-corp techx-infrastructure-app -n argocd
```

Prometheus live validation should prove that the new node-agent exports without
breaking the already-working gateway path:

```promql
sum(rate(otelcol_receiver_accepted_metric_points_total{service_name=~".*node.*|otel-node-agent"}[5m]))
sum(rate(otelcol_exporter_sent_metric_points_total{service_name=~".*node.*|otel-node-agent", exporter="otlphttp/prometheus"}[5m]))
sum(rate(otelcol_exporter_send_failed_metric_points_total{service_name=~".*node.*|otel-node-agent"}[5m]))
```

Do not delete or disable the old `otel-collector-agent` in this PR. Deletion is
only safe after the node-agent has been live long enough to compare host/kubelet
metric continuity and no Prometheus exporter failures are observed.
