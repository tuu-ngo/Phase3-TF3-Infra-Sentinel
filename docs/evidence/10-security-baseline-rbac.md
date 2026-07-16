# Security Assessment — RBAC & Service Account Token Exposure

## Owner
PNV (CDO01)

## Assessment Metadata

| Field | Value |
|---|---|
| Assessment Date | 2026-07-09 |
| Cluster | techx-corp-tf3 |
| Region | ap-southeast-1 |
| Namespace | techx-tf3 |
| Assessor | PNV (CDO01) |
| Methodology | Live cluster enumeration via `kubectl auth can-i`, RBAC manifest review |

---

## Executive Summary

Assessment Date: 2026-07-09
Cluster: techx-corp-tf3

| Severity | Count |
|---|---|
| HIGH | 1 |
| MEDIUM | 1 |
| INFORMATIONAL | 1 |

No active compromise was observed. However, two misconfigurations violate the principle of
least privilege and may significantly increase blast radius if any workload is compromised.
Both findings require only YAML changes and a `helm upgrade` — estimated remediation effort
is less than one day with near-zero cost.

**Expected risk reduction after remediation: High**

---

## Scope

Enumerated all ServiceAccounts, Roles, ClusterRoles, RoleBindings, and ClusterRoleBindings
in namespace `techx-tf3` and cluster-wide. Verified actual permissions using `kubectl auth can-i`
impersonation. Inspected `automountServiceAccountToken` setting on all 25 deployments.

## Commands Executed

```bash
# Enumerate SA, roles, bindings
kubectl -n techx-tf3 get serviceaccount -o wide
kubectl -n techx-tf3 get rolebinding,clusterrolebinding -o wide
kubectl get clusterrole grafana-clusterrole -o yaml
kubectl get clusterrole otel-collector -o yaml
kubectl get clusterrole prometheus -o yaml
kubectl -n techx-tf3 get role grafana -o yaml

# Permission verification via impersonation
kubectl auth can-i --list --as=system:serviceaccount:techx-tf3:grafana
kubectl auth can-i get secrets  --as=system:serviceaccount:techx-tf3:grafana
kubectl auth can-i list secrets --as=system:serviceaccount:techx-tf3:grafana
kubectl auth can-i list secrets --as=system:serviceaccount:techx-tf3:grafana -n kube-system
kubectl auth can-i --list --as=system:serviceaccount:techx-tf3:techx-corp

# automountServiceAccountToken audit across all deployments
kubectl -n techx-tf3 get deploy -o json | python -c "<script>"

# Secrets inventory (names only, values never retrieved)
kubectl get secrets --all-namespaces --no-headers
kubectl -n techx-tf3 get secret grafana -o json | python -c "print keys only"
```

---

## Finding Summary

**Expected:**
- `grafana-clusterrole` grants secret read access only within namespace `techx-tf3`
- Business pods do not mount a ServiceAccount token if they have no reason to call the Kubernetes API

**Observed:**
- `grafana-clusterrole` is a **ClusterRole** granting `get/list/watch` on `secrets` cluster-wide,
  including namespace `kube-system`
- **22 out of 25 business deployments** mount the `techx-corp` ServiceAccount token by default,
  with no explicit `automountServiceAccountToken: false` set

---

## FINDING-01

**Title:** Grafana ServiceAccount Can Read Secrets Cluster-Wide

**Severity:** HIGH

**Reason:**
- Privilege scope: Cluster-wide (not namespace-scoped)
- Sensitive resources: `secrets` (includes credentials, TLS certs, Helm release values)
- Exploit complexity: Low — requires only possession of the Grafana pod's mounted SA token
- Impact: Credential disclosure and potential cluster compromise via secrets enumeration

**CWE:** CWE-269: Improper Privilege Management

**Description:**

The Grafana ServiceAccount (`techx-tf3/grafana`) is bound to a `ClusterRole` named
`grafana-clusterrole` via a `ClusterRoleBinding`. The ClusterRole grants `get`, `watch`,
and `list` on `secrets` across all namespaces. The current deployment uses the upstream Grafana Helm chart
configuration, resulting in cluster-wide secret read permissions.

```yaml
# kubectl get clusterrole grafana-clusterrole -o yaml (actual output)
rules:
- apiGroups: [""]
  resources:
  - configmaps
  - secrets          # cluster-wide read access
  verbs:
  - get
  - watch
  - list
```

**Evidence:**

```bash
$ kubectl auth can-i get secrets \
    --as=system:serviceaccount:techx-tf3:grafana
yes

$ kubectl auth can-i list secrets \
    --as=system:serviceaccount:techx-tf3:grafana
yes

$ kubectl auth can-i list secrets \
    --as=system:serviceaccount:techx-tf3:grafana \
    -n kube-system
yes
```

**Impact — Secrets readable by Grafana SA (11 total, names only):**

| Namespace | Secret Name | Type | Sensitivity |
|---|---|---|---|
| `kube-system` | `aws-load-balancer-tls` | `kubernetes.io/tls` | TLS private key |
| `kube-system` | `sh.helm.release.v1.aws-lb.v1` | `helm.sh/release.v1` | LB config |
| `kube-system` | `sh.helm.release.v1.metrics-server.v1` | `helm.sh/release.v1` | — |
| `techx-tf3` | `grafana` | `Opaque` | `admin-password`, `admin-user`, `ldap-toml` |
| `techx-tf3` | `sh.helm.release.v1.techx-corp.v1~v7` | `helm.sh/release.v1` | **Full Helm values across 7 revisions, may contain flagd sync token** |

Helm release secrets are base64+gzip encoded but trivially decodable. An attacker with
access to the Grafana SA token can enumerate all 7 Helm revisions to reconstruct the full
deployment configuration including any secrets passed via `-f values-flagd-sync.yaml`.

**Attack Scenario:**

```
Attacker
  ↓ Exploit Grafana vulnerability (e.g., CVE-2021-43798 path traversal,
    malicious plugin, or SSRF via datasource)
  ↓ Steal SA token from /var/run/secrets/kubernetes.io/serviceaccount/token
  ↓ Authenticate to Kubernetes API using stolen token
  ↓ List and read secrets across all namespaces
  ↓ Credential theft: admin-password, TLS private key, flagd sync token
  ↓ Potential credential disclosure, lateral movement, and increased risk of cluster compromise.
```

**Recommendation:**

Replace the `ClusterRole` + `ClusterRoleBinding` with a namespace-scoped `Role` +
`RoleBinding`. Grafana only needs to read secrets within its own namespace (`techx-tf3`).

```yaml
# Replace existing ClusterRole with namespace-scoped Role
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: grafana
  namespace: techx-tf3
rules:
- apiGroups: [""]
  resources: ["configmaps", "secrets"]
  verbs: ["get", "watch", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: grafana
  namespace: techx-tf3
subjects:
- kind: ServiceAccount
  name: grafana
  namespace: techx-tf3
roleRef:
  kind: Role
  name: grafana
  apiGroup: rbac.authorization.k8s.io
```

Override in Helm values to prevent the chart from recreating the ClusterRole:
```yaml
grafana:
  rbac:
    create: true
    useExistingRole: grafana
    pspEnabled: false
    namespaced: true      # disables ClusterRole creation in chart
```

**Verification:**

```bash
$ kubectl auth can-i list secrets \
    --as=system:serviceaccount:techx-tf3:grafana \
    -n kube-system
no    # expected after fix
```

---

## FINDING-02

**Title:** Business Workloads Automatically Mount ServiceAccount Tokens

**Severity:** MEDIUM

**Reason:**
- Exploitability: Requires prior pod compromise (RCE, SSRF, or container escape)
- Impact today: Limited — `techx-corp` SA has no Kubernetes API permissions currently
- Future risk: Elevated, because any new RoleBinding granted to the shared ServiceAccount immediately becomes available to all mounted workloads. — any future `RoleBinding` on `techx-corp` SA immediately exposes
  all 22 business pods, with no additional configuration required
- Defense-in-depth: Mounted tokens create unnecessary attack surface in violation of
  least-privilege principle

**CWE:** CWE-250: Execution with Unnecessary Privileges

**Description:**

All 22 business deployments use the `techx-corp` ServiceAccount without setting
`automountServiceAccountToken: false`. Kubernetes defaults this to `true`, meaning every
business pod has a valid JWT token mounted at
`/var/run/secrets/kubernetes.io/serviceaccount/token`.

None of the 22 services require Kubernetes API access — they communicate exclusively via
gRPC with each other. The token provides no legitimate operational value to these pods.

**Evidence:**

```
DEPLOY               AUTOMOUNT_SPEC              SA
------------------------------------------------------------
accounting           NOT SET (defaults True)     techx-corp
ad                   NOT SET (defaults True)     techx-corp
cart                 NOT SET (defaults True)     techx-corp
checkout             NOT SET (defaults True)     techx-corp
currency             NOT SET (defaults True)     techx-corp
email                NOT SET (defaults True)     techx-corp
flagd                NOT SET (defaults True)     techx-corp
fraud-detection      NOT SET (defaults True)     techx-corp
frontend             NOT SET (defaults True)     techx-corp
frontend-proxy       NOT SET (defaults True)     techx-corp
image-provider       NOT SET (defaults True)     techx-corp
kafka                NOT SET (defaults True)     techx-corp
llm                  NOT SET (defaults True)     techx-corp
load-generator       NOT SET (defaults True)     techx-corp
payment              NOT SET (defaults True)     techx-corp
postgresql           NOT SET (defaults True)     techx-corp
product-catalog      NOT SET (defaults True)     techx-corp
product-reviews      NOT SET (defaults True)     techx-corp
quote                NOT SET (defaults True)     techx-corp
recommendation       NOT SET (defaults True)     techx-corp
shipping             NOT SET (defaults True)     techx-corp
valkey-cart          NOT SET (defaults True)     techx-corp
```

Current `techx-corp` SA permission check confirms no active Kubernetes API privileges:

```bash
$ kubectl auth can-i --list \
    --as=system:serviceaccount:techx-tf3:techx-corp
# Result: only selfsubjectreviews + public non-resource URLs
# No permissions over any Kubernetes resources
```

**Current impact:** No direct privilege over Kubernetes resources via this token today.

**Potential impact:** Any future `RoleBinding` addition to the `techx-corp` SA — whether
intentional (a developer adds K8s API access for a new feature) or accidental (copy-paste
from a template) — immediately exposes all 22 business pods to that new privilege, because
the token is already mounted everywhere with no additional action required. RBAC drift of
this type is common in long-lived clusters.

**Attack Path:**

```
RCE/SSRF in any business pod (e.g., checkout, product-catalog, llm)
  ↓ Read mounted JWT at /var/run/secrets/kubernetes.io/serviceaccount/token
  ↓ Authenticate to Kubernetes API
  ↓ [Today] Limited — no resource permissions
  ↓ [After RBAC drift] Enumerate pods, read configmaps, or escalate further
  ↓ Lateral movement within cluster
```

**Recommendation:**

Add `automountServiceAccountToken: false` to the pod spec of all 22 business deployments.
This is a one-line change per component and requires no application code changes.

```yaml
# In Helm chart: templates/component.yaml or values.yaml override
spec:
  template:
    spec:
      automountServiceAccountToken: false
```

**Verification:**

```bash
$ kubectl -n techx-tf3 exec deploy/checkout -- \
    ls /var/run/secrets/kubernetes.io/serviceaccount/
# Expected: ls: /var/run/secrets/kubernetes.io/serviceaccount/: No such file or directory
```

---

## FINDING-03 (Informational)

**Title:** Grafana Secret Contains Admin Credentials

**Severity:** INFORMATIONAL

**Description:**
The `grafana` secret in `techx-tf3` contains keys `admin-user` and `admin-password`.
These are the default Grafana admin credentials generated at Helm install time.
If the default password was not rotated after deployment, or if it is a weak/predictable
value, the Grafana admin interface is accessible to anyone with network access through
`frontend-proxy` at `http://<host>:8080/grafana/`.

**Note:** Values were not retrieved during this assessment. Only key names were inspected.

**Recommendation:**
Verify the admin password was rotated post-deploy. Consider adding Grafana behind
authentication (OAuth2 proxy or similar) rather than exposing it through `frontend-proxy`
to end users.

---

## Backlog Proposal

| ID | Finding | Severity | Effort | Priority |
|---|---|---|---|---|
| SEC-01 | Restrict Grafana Secret Access: ClusterRole → namespaced Role | HIGH | XS | P1 |
| SEC-02 | Disable SA Token Automount on all business pods | MEDIUM | XS | P1 |
| SEC-03 | Verify and rotate Grafana admin credentials | INFO | XS | P2 |

**XS = Extra Small** — all three fixes are YAML-only changes, no infrastructure cost,
deployable in a single `helm upgrade`.

### SEC-01 detail
- **Item**: Replace `grafana-clusterrole` (ClusterRole) + `grafana-clusterrolebinding`
  (ClusterRoleBinding) with a namespace-scoped `Role` + `RoleBinding` in `techx-tf3`
- **Why now**: Active HIGH finding with confirmed blast radius into `kube-system`
- **Cost**: $0 — YAML change + helm upgrade
- **Rollback**: `helm rollback techx-corp <REVISION> -n techx-tf3`
- **Verification**: `kubectl auth can-i list secrets --as=... -n kube-system` → `no`

### SEC-02 detail
- **Item**: Add `automountServiceAccountToken: false` to all 22 business deployments
- **Why now**: Defense-in-depth — prevents token from existing in pod filesystem.
  Cheapest hardening available; cost of not doing it grows with every new RoleBinding added
- **Cost**: $0 — 1 line YAML per component
- **Rollback**: Remove the flag, `helm upgrade`
- **Verification**: `kubectl exec deploy/checkout -- ls /var/run/secrets/...` → `No such file`

---

*Document classification: Internal — TF3 Security Assessment*
*Report format: Kubernetes RBAC Security Assessment (aligned with AWS Security Review / NCC Group style)*
