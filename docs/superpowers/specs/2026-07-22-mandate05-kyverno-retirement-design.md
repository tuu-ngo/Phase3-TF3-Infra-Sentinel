# Mandate 05 Kyverno Retirement Design

## Status

- Design approved in conversation on 2026-07-22.
- This document authorizes repository planning only. It does not authorize a
  production sync, prune, patch, or other Kubernetes mutation.

## Goal

Retire Kyverno from the Mandate 05 admission path and return Argo CD to a
clean, fully reconciled state only after Kubernetes-native controls prove the
required coverage without reducing production workload readiness or customer
SLOs.

Mandate 10 is not implemented yet and is outside this retirement. Its future
admission design will use a dedicated signature/provenance verification
webhook together with ValidatingAdmissionPolicy (VAP), not Kyverno.

## Current Verified State

The live baseline captured on 2026-07-22 showed:

- all seven Argo CD control-plane pods Ready with zero restarts;
- thirteen Argo CD Applications Healthy, with `flagd-secret-sync` and
  `techx-corp-bootstrap` OutOfSync;
- `techx-corp-bootstrap` retaining the deleted `kyverno` child Application as
  `requiresPruning=true` because the live root Application does not currently
  have automated prune/self-heal enabled;
- four Kyverno ClusterPolicies Ready in `Audit` mode;
- two native VAP bindings enforcing `Deny` for image-reference and explicit
  resource requirements outside `kube-system`;
- Pod Security Admission (PSA) `restricted` enforcement on the application and
  normal platform namespaces;
- `observability-system` intentionally remaining at PSA `warn/audit`, because
  its telemetry workloads are not yet compatible with Restricted enforcement;
- `argocd-self` currently Synced/Healthy but retaining a failed operation from
  a client-side apply of the large `applicationsets.argoproj.io` CRD;
- `flagd-secret-sync` reporting a separate ExternalSecret drift that is not
  part of admission-controller retirement.

## Scope

### In scope

- prove that native VAP and PSA cover the Mandate 05 admission requirements;
- preserve the intentional PSA exceptions for `observability-system` and
  Kubernetes system namespaces;
- remove the four Mandate 05 Kyverno ClusterPolicy declarations and their Argo
  CD child Application;
- complete deletion of the already-removed Kyverno controller Application in a
  safe prune order;
- update ADR/evidence text so it no longer claims that Kyverno must be retained
  for the not-yet-implemented Mandate 10;
- enable Server-Side Apply for `argocd-self` so large CRDs can reconcile without
  the client-side last-applied annotation limit;
- define the monitored bootstrap reconciliation and post-retirement gates.

### Out of scope

- designing or implementing the Mandate 10 verification webhook;
- changing PSA on `observability-system` from warn/audit to enforce;
- weakening or disabling the native VAP bindings;
- changing `flagd`, OpenFeature hooks, `/flagservice`, or Envoy fault injection;
- resolving the `ExternalSecret/postgres-connection` drift in the same PR;
- manually deleting Kyverno objects or manually syncing child Applications;
- unrelated workload, Terraform, cost, or observability refactors.

## Admission Coverage Contract

| Mandate 05 control | Native owner | Required enforcement |
| --- | --- | --- |
| Explicit CPU and memory requests and limits | `mandate05-native-resource-requirements` VAP and binding | `Deny` outside `kube-system` |
| No explicit or implicit `latest` image reference | `mandate05-native-image-reference` VAP and binding | `Deny` outside `kube-system` |
| First-party ECR images pinned to a sha256 digest | `mandate05-native-image-reference` VAP and binding | `Deny` outside `kube-system` |
| Non-root, non-privileged runtime baseline | PSA Restricted | Enforce on application and normal platform namespaces |
| Linux capabilities, privilege escalation, and seccomp baseline | PSA Restricted | Enforce on application and normal platform namespaces |
| Telemetry workloads that are not Restricted-compatible | PSA namespace labels | `observability-system` remains warn/audit only |
| Kubernetes control-plane add-ons | Native selectors and PSA namespace policy | `kube-system` remains an explicit system exception |

No implementation may broaden either exception beyond these named boundaries.
Future non-system namespaces must receive an explicit PSA decision rather than
silently inheriting an undocumented gap.

## Delivery Design

### Stage 1: Evidence and desired-state correction

Use an isolated branch from the newest `origin/main`. The implementation PR
will:

1. add deterministic tests for the native admission coverage matrix;
2. remove `gitops/apps/kyverno-policies-app.yaml` and the four policy manifests
   under `gitops/policies/kyverno/`;
3. retire or replace Kyverno-specific tests with native VAP/PSA evidence so CI
   no longer depends on a component that desired state removes;
4. update Mandate 05 ADR/evidence statements to establish the Mandate 10
   webhook-plus-VAP boundary;
5. add `ServerSideApply=true` to the `argocd-self` Application sync options;
6. retain sync wave `20` semantics for policy retirement evidence and document
   the existing controller Application wave `10` deletion boundary.

The PR must not include the ExternalSecret drift or any production mutation.

### Stage 2: Monitored bootstrap reconciliation

After the PR is merged and all preflight gates pass, an explicitly approved
production window will reconcile only the bootstrap root declaration so that
the live `techx-corp-bootstrap` Application receives the repository-declared
automated prune/self-heal policy.

Argo CD processes higher waves first during pruning. The Kyverno policy
Application uses wave `20` and the removed controller Application used wave
`10`, so policy resources are pruned before the controller. If pruning wave 20
fails, Argo must stop before wave 10. Selective sync is forbidden because it
does not provide the intended full-wave lifecycle and can bypass hooks.

No operator will manually delete Kyverno CRDs, webhooks, policies, workloads,
or namespaces. Argo CD remains the owner of the retirement.

## Verification Gates

### Pre-merge repository gates

- parse every changed YAML file successfully;
- run the existing native-policy validation suite and any new retirement tests;
- prove that a compliant Pod manifest passes;
- prove that missing resource declarations are denied by the resource VAP;
- prove that explicit latest, implicit latest, and an unpinned first-party image
  are denied by the image VAP;
- prove that a root/privileged Pod is denied by PSA in `techx-tf3`;
- prove that the same PSA fixture does not become an enforced rejection in
  `observability-system`, while warning/audit labels remain present;
- render all exact production Helm/GitOps values and submit the rendered
  workload objects with server-side dry-run;
- verify the `argocd-self` render contains `ServerSideApply=true` and no
  unrelated resource change;
- run `git diff --check` and confirm every changed line maps to this design.

### Pre-reconcile live gates

- AWS account is `197826770971` and the principal is the expected
  `cdo-admin-team` identity;
- the SSM tunnel and Kubernetes context are healthy;
- `native-admission-policies` is Synced/Healthy and both bindings use `Deny`;
- all expected PSA namespace labels match the coverage contract;
- native negative fixtures are rejected by server-side dry-run and the good
  fixture is accepted;
- current production workload render passes server-side dry-run;
- checkout request volume is non-zero and the current SLO evidence is within
  threshold;
- Argo CD control-plane pods are Ready and stable.

Any failed gate is a NO-GO. A failed or unavailable SLO query is UNKNOWN, not a
pass.

### Post-reconcile success criteria

- no `kyverno` or `kyverno-policies` Argo CD Application remains;
- no Kyverno Deployment, StatefulSet, admission webhook configuration,
  ClusterPolicy, PolicyException, or Kyverno-owned CRD remains unexpectedly;
- all intentionally retained Applications are Synced/Healthy;
- `techx-corp-bootstrap` has no `requiresPruning` resource;
- the latest `argocd-self` operation is Succeeded and its Application is
  Synced/Healthy;
- native VAP bindings remain `Deny` and PSA labels remain unchanged;
- all production workloads remain Ready with no retirement-related warning
  events;
- storefront and product smoke probes return HTTP 200;
- checkout, browse, cart, and frontend latency SLO evidence remains within the
  project thresholds with non-zero traffic.

Argo health alone is not sufficient evidence of success.

## Failure Handling and Rollback

Before reconcile, rollback is a Git revert and no production change occurs.

During prune:

- if wave 20 fails, stop and investigate; do not force-delete finalizers or
  continue to the controller wave;
- if native admission rejects a legitimate manifest, revert the retirement PR
  through Git and let Argo restore the Kyverno Applications; do not disable PSA
  or VAP as the first response;
- if the Argo control plane becomes unhealthy, stop all further reconciliation
  and use the reviewed bootstrap manifest to restore the last known-good Argo
  declaration under an explicitly approved recovery action log;
- if customer SLO degrades, stop the change, preserve evidence, and follow the
  incident process before continuing.

Rollback is complete only when the intended Applications are Synced/Healthy,
admission dry-runs produce the expected results, workload readiness recovers,
and customer-path evidence is healthy.

## Separate GitOps-Clean Follow-up

The ExternalSecret drift belongs to a separate investigation and PR. Its exact
JSON path must be identified without printing secret values. A narrow
`ignoreDifferences` rule is acceptable only for a controller-owned/defaulted
field; a real desired-state mismatch must be corrected in the manifest. The
entire ExternalSecret spec must never be ignored.

GitOps is fully clean only after both the Kyverno retirement and this separate
drift remediation have reconciled successfully.

## Authoritative Behavior References

- Argo CD sync waves and reversed prune order:
  <https://argo-cd.readthedocs.io/en/latest/user-guide/sync-waves/>
- Argo CD Server-Side Apply for resources exceeding the last-applied annotation
  limit:
  <https://argo-cd.readthedocs.io/en/release-2.5/user-guide/sync-options/#server-side-apply>
- Kubernetes ValidatingAdmissionPolicy behavior:
  <https://kubernetes.io/docs/reference/access-authn-authz/validating-admission-policy/>
- Kubernetes admission webhook operational guidance for the future Mandate 10
  verifier:
  <https://kubernetes.io/docs/concepts/cluster-administration/admission-webhooks-good-practices/>
