# PM-149 — RBAC least privilege evidence

Status: implementation evidence template; production verification is pending an
operator identity with ServiceAccount impersonation and `pods/exec` permission.

## Scope

PM-149 closes only:

- SEC-01: Grafana cluster-wide Secret read access.
- SEC-02: unnecessary Kubernetes API token automount for workloads using the
  shared `techx-corp` ServiceAccount.

This evidence does not claim completion of the remaining Mandate 17 findings,
per-service ServiceAccount migration, NetworkPolicy work, Terraform changes, or
flagd changes.

## Environment metadata

| Field | Value |
|---|---|
| Cluster | `techx-corp-tf3` |
| Account | `197826770971` |
| Region | `ap-southeast-1` |
| Namespace | `techx-tf3` |
| Git branch | `feat/pm-149-mandate17-rbac-least-privilege` |
| Git commit | fill after implementation |
| PR | fill after opening |
| Argo revision | fill after reconciliation |
| Readonly verifier | fill identity |
| Privileged verifier | fill identity |

## Render evidence

Authoritative render must use a temporary chart copy and this values order:

```text
phase3 - information/techx-corp-chart/values.yaml
phase3 - information/deploy/values-flagd-sync.yaml
phase3 - information/deploy/values-prod.yaml
phase3 - information/deploy/values-aio-llm.yaml
```

Record:

- Helm version and command;
- rendered checksum;
- rendered Grafana `Role` and `RoleBinding`;
- absence of Grafana-owned `ClusterRole` and `ClusterRoleBinding`;
- dynamic list of workloads whose `serviceAccountName` is `techx-corp`;
- `automountServiceAccountToken: false` assertion for every shared-SA workload;
- `product-reviews-bedrock` ServiceAccount and IRSA annotation assertion.

Do not store rendered Secret values or ServiceAccount tokens.

## Live verification

The privileged verifier must record the command, timestamp, and result for:

```bash
kubectl auth can-i list secrets \
  --as=system:serviceaccount:techx-tf3:grafana \
  -n kube-system

kubectl auth can-i list secrets \
  --as=system:serviceaccount:techx-tf3:grafana \
  -n techx-tf3

kubectl -n techx-tf3 get role,rolebinding
kubectl get clusterrole,clusterrolebinding
kubectl -n techx-tf3 get serviceaccount techx-corp \
  -o jsonpath='{.automountServiceAccountToken}{"\n"}'
kubectl -n techx-tf3 get deploy -o json
kubectl -n techx-tf3 get pods -o json
```

Expected:

- Grafana cannot list Secrets in `kube-system`;
- Grafana can list required Secrets in `techx-tf3`;
- Grafana namespaced Role/RoleBinding exists;
- Grafana-owned cluster RBAC is absent after Argo prune;
- every current shared-SA workload has Pod-template automount `false`;
- newly created shared-SA Pods have no `kube-api-access-*` volume;
- `product-reviews` still uses `product-reviews-bedrock`.

If readonly access returns `Forbidden`, record the exact error and mark the
check inconclusive; do not interpret it as a security pass.

## Availability and smoke tests

Record:

- Argo `Synced/Healthy`;
- all expected Deployments available;
- checkout Rollout healthy;
- Grafana HTTP health through the approved Cloudflare Access path;
- products and cart smoke tests;
- approved checkout flow;
- unchanged flag evaluation behavior;
- no repeated Grafana sidecar `Forbidden` errors;
- no IRSA/WebIdentity errors from product-reviews.

## Rollback readiness

| Field | Value |
|---|---|
| PM-149 merge commit | fill after merge |
| Revert branch/PR | fill before merge |
| Rollback owner | fill before merge |
| Argo expected behavior | reconcile reverted Git state; no manual live patch |
