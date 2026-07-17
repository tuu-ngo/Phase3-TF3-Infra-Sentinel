# TF3 IAM and EKS Production Access Design

**Date:** 2026-07-17  
**Status:** Approved design; implementation pending  
**Scope:** IAM identities, shared operator/read-only roles, EKS access entries, and namespace RBAC  
**Explicitly out of scope:** Argo CD `AppProject`, live workload changes, NetworkPolicy changes, and removal of existing administrator access

## Objective

Reduce the risk of unreviewed manual production changes while preserving an audited operator path for the PM and TL of CDO01 and CDO02. Argo CD remains the normal deployment principal. Human access is split into a namespaced operator role and a read-only role.

The change must not restart workloads, alter customer traffic, modify `flagd`, or mutate any current production application resource.

## Current State

The production Terraform root passes `eks_admin_principal_arns` to the EKS module. Each listed principal receives `AmazonEKSClusterAdminPolicy` with cluster scope. The current production variables list only `arn:aws:iam::197826770971:user/cdo-2-admin-team`.

That model grants a daily-use IAM user unrestricted Kubernetes administration. It does not separate routine observation, namespaced workload operation, and cluster-level emergency administration.

## Identities

Create four individual operator IAM users:

- `cdo01-pm`
- `cdo01-tl`
- `cdo02-pm`
- `cdo02-tl`

Create one shared read-only IAM user:

- `tf3-members-readonly`

The shared read-only identity is an accepted temporary trade-off. It cannot attribute activity to an individual member and requires password rotation whenever membership changes. Its permissions are therefore intentionally non-mutating and exclude secret access and pod execution.

## Login Profiles and Credential Handling

Each user receives an AWS console login profile with a generated random temporary password.

- The four individual operator users must change their password on first login.
- The shared read-only user does not force a first-login password change because the first member to change it would lock out the others.
- Each user receives one access key for local AWS CLI authentication. The key has no direct production permission; it can only use the source user's limited IAM policy and assume the assigned shared role.
- MFA is not required by the role trust policies, per the approved scope.
- Role session-name format is not constrained, per the approved scope.
- No password, access-key ID, or secret access key may appear in Terraform state, Git, command arguments, terminal output, chat, or tool output.
- Bootstrap passwords and access keys are generated at execution time and written only to a local `0600` handoff file outside the repository.
- The handoff file path is reported after successful creation; the file must be securely deleted after credentials are distributed.

IAM users, login profiles, and the initial access keys are created through an audited bootstrap procedure rather than Terraform because storing generated credentials in Terraform inputs or state would create avoidable credential exposure.

## IAM Role Model

### `tf3-production-operator`

The trust policy allows only the four individual PM/TL IAM user ARNs to call `sts:AssumeRole`.

The source users receive only:

- permission to assume `tf3-production-operator`;
- permission to change their own IAM console password.

The role receives an EKS access entry mapped to Kubernetes group `tf3-production-operators`. It does not receive `AmazonEKSClusterAdminPolicy` or another broad EKS access policy.

### `tf3-production-readonly`

The trust policy allows only `tf3-members-readonly` to call `sts:AssumeRole`.

The source user receives only:

- permission to assume `tf3-production-readonly`.

The shared user cannot change its own password. An administrator performs intentional password rotation so one member cannot unexpectedly invalidate access for the rest of the group.

The role receives an EKS access entry mapped to Kubernetes group `tf3-production-readers`. It does not receive an EKS cluster access policy.

## Kubernetes RBAC

RBAC is declared under `gitops/infrastructure/` and reconciled by `techx-infrastructure-app`. Human IAM principals are not granted permission to modify their own Role or RoleBinding.

### Operator permissions

The `tf3-production-operator` group is bound to a namespaced Role in `techx-tf3`.

Allowed read operations:

- `get`, `list`, and `watch` pods, pod status, events, Services, EndpointSlices, Deployments, ReplicaSets, StatefulSets, Jobs, CronJobs, HPAs, PDBs, Rollouts, AnalysisRuns, ConfigMaps, and NetworkPolicies;
- read pod logs;
- read resource metrics through the existing metrics API;
- create `pods/portforward` for private operational access.

Allowed mutation operations:

- `create`, `update`, and `patch` Deployments, Jobs, CronJobs, and ConfigMaps in `techx-tf3`;
- `update` and `patch` Deployment scale subresources;
- `update` and `patch` Argo Rollout resources and their scale subresources;
- delete Pods only, enabling a controlled restart while leaving the owning controller intact.

Explicitly denied by omission:

- Secrets and service-account token resources;
- `pods/exec`, `pods/attach`, and ephemeral containers;
- Roles, RoleBindings, ClusterRoles, and ClusterRoleBindings;
- NetworkPolicy mutation;
- PVC/PV mutation or deletion;
- Namespace mutation;
- StatefulSet mutation;
- Service, EndpointSlice, Ingress, and LoadBalancer mutation;
- ServiceAccount mutation;
- Argo CD Application and AppProject mutation;
- Kyverno policy, admission webhook, CRD, node, Karpenter, and other cluster-scoped mutation;
- mutation in `argocd`, `kube-system`, `kyverno`, or any namespace other than `techx-tf3`.

Normal deployment still goes through PR, CI, and Argo CD. Operator mutations are an incident containment path and must be reconciled into Git before closure.

### Read-only permissions

The `tf3-production-readonly` group is bound to a namespaced Role in `techx-tf3`.

Allowed:

- `get`, `list`, and `watch` the same non-secret operational resources;
- read pod logs and events;
- read resource metrics;
- create `pods/portforward` for approved private dashboards and service observation.

Not allowed:

- any resource mutation;
- Secret reads;
- ConfigMap reads, because ConfigMaps can contain sensitive runtime configuration despite not being Kubernetes Secrets;
- `pods/exec`, `pods/attach`, or ephemeral containers;
- access outside `techx-tf3`.

## Resource Ownership

Terraform owns:

- IAM roles and trust policies;
- source-user assume-role policies;
- EKS access entries and Kubernetes group mappings.

GitOps owns:

- the namespaced operator Role and RoleBinding;
- the namespaced read-only Role and RoleBinding.

Bootstrap procedure owns:

- IAM user creation;
- console login-profile creation;
- initial access-key creation;
- local credential handoff file.

This separation keeps credentials out of Terraform state while keeping durable authorization policy reviewable and reproducible.

## Rollout Order

1. Add the Kubernetes Roles and RoleBindings through GitOps.
2. Verify Argo CD reports `techx-infrastructure-app` as `Synced/Healthy`; no workload should roll.
3. Create the five IAM users and login profiles with the bootstrap procedure. At this point the users have no production permissions.
4. Add IAM roles, assume-role policies, source-user policy attachments, and EKS access entries through Terraform.
5. Run `terraform plan` and require review before apply.
6. Apply the reviewed Terraform plan through the production workflow.
7. Test each role using impersonation and real assumed-role credentials.
8. Confirm storefront and business SLOs are unchanged.
9. Keep the existing `cdo-2-admin-team` cluster-admin entry until all positive and negative tests pass.
10. Handle cluster-admin reduction in a separate approved change with an explicit recovery path.

## Verification Matrix

Operator role must pass:

- list pods and read logs in `techx-tf3`;
- port-forward an approved Service;
- patch a disposable test Deployment or use server-side dry-run for production workload permissions;
- scale a Deployment through its scale subresource;
- inspect NetworkPolicies without modifying them.

Operator role must fail:

- read a Secret;
- exec into a Pod;
- create or patch a NetworkPolicy;
- patch a StatefulSet;
- delete a PVC;
- create a RoleBinding;
- patch an Argo CD Application;
- mutate a resource in `argocd`, `kube-system`, or `kyverno`.

Read-only role must pass:

- list pods and workloads;
- read pod logs and events;
- read metrics;
- port-forward an approved Service.

Read-only role must fail:

- patch or delete any workload;
- read Secrets or ConfigMaps;
- exec into a Pod;
- create a NetworkPolicy;
- access another namespace.

Verification uses `kubectl auth can-i`, server-side dry-run where appropriate, and a real assumed-role session for at least one operator and the shared reader. No production resource is mutated merely to prove denial.

## Safety and Rollback

This design changes only identity and authorization objects. It does not change application manifests, pod templates, Services, NetworkPolicies, data stores, or edge routing, so it should not cause customer downtime.

Rollback order:

1. Preserve the existing administrator entry throughout initial rollout.
2. Remove or disable the new EKS access entries if mapping is incorrect.
3. Revert the GitOps RBAC commit if the Roles are incorrect.
4. Remove source-user assume-role permissions.
5. Delete login profiles before deleting unused IAM users.
6. Delete the local credential handoff file after credential revocation or successful distribution.

No rollback step may remove the Argo CD service account's deployment authority or the existing verified recovery path.

## Audit and Operational Rules

- Normal changes remain PR → CI → Argo CD.
- Operator role use requires an incident or approved change record even though the trust policy does not enforce MFA or session-name formatting.
- Any manual containment action must record actor, UTC timestamp, command, resource, reason, and resulting SLO state.
- Manual desired-state changes must be codified in Git before incident closure.
- The shared read-only password is rotated whenever membership changes or exposure is suspected.
- Each individual access key is rotated at least every 90 days and immediately when exposure is suspected.
- The shared read-only access key and password are rotated whenever membership changes.
- No credential is transmitted through Git, chat, ticket text, or screenshots.

## Acceptance Criteria

- All five IAM users exist with console login profiles and exactly one active access key each.
- Four individual users can assume only the operator role; the shared user can assume only the read-only role.
- Operator and read-only permissions match the verification matrix.
- Argo CD remains `Synced/Healthy`.
- No application pod restarts as a result of the access rollout.
- Storefront smoke probes and business SLOs show no regression.
- Existing cluster-admin access remains unchanged until a separately approved de-privileging change.
- Temporary passwords and initial access keys are delivered from a `0600` local handoff file and that file is deleted after distribution.
