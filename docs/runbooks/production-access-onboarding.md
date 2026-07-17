# Production IAM and EKS Access Runbook

## Scope and safety gates

This runbook creates four individual operator identities (`cdo01-pm`, `cdo01-tl`, `cdo02-pm`, `cdo02-tl`) and the shared `tf3-members-readonly` identity in AWS account `197826770971`.

- Normal changes remain PR → CI → Argo CD.
- Do not remove cdo-2-admin-team; de-privileging cluster-admin is a separate approved change.
- Do not create an AppProject or change workloads, NetworkPolicies, data stores, edge routing, Secrets, `flagd`, `/flagservice`, or Envoy fault injection.
- Stop if the AWS account differs from `197826770971`, the Terraform plan contains unrelated changes, Argo is unhealthy, or business SLOs are below threshold.
- The target is one active access key per user. Never create a second key during onboarding.

## Phase 1: Merge RBAC through GitOps

Validate locally:

```bash
python3 -m pytest scripts/ci/test_production_access_contract.py -q
kubectl apply --dry-run=client -f gitops/infrastructure/rbac-production-access.yaml
```

Merge the PR and let Argo CD reconcile `gitops/infrastructure/rbac-production-access.yaml`. Do not manually apply it to production. Verify:

```bash
kubectl -n argocd get application techx-infrastructure-app
kubectl -n techx-tf3 get role,rolebinding | grep tf3-production
kubectl -n techx-tf3 get pods
```

Require `Synced/Healthy`, two Roles, two RoleBindings, and no application pod restart caused by this change.

## Phase 2: Bootstrap source identities

Verify the caller before mutation:

```bash
aws sts get-caller-identity --query Account --output text
```

The result must be `197826770971`. Create a protected temporary directory and choose a file that does not yet exist; the bootstrap refuses overwrite:

```bash
TF3_HANDOFF_DIR="$(mktemp -d /tmp/tf3-access-handoff.XXXXXX)"
chmod 700 "$TF3_HANDOFF_DIR"
python3 scripts/access/bootstrap_iam_users.py --output "$TF3_HANDOFF_DIR/credentials.json"
stat -c '%a %n' "$TF3_HANDOFF_DIR/credentials.json"
```

Expected mode is `600`. Do not use `set -x`, redirect command output to shared logs, print the file, or place its contents in Git, chat, tickets, screenshots, shell history, or Terraform state. The source users have no production authority until the reviewed Terraform policy attachments exist.

## Phase 3: Review and apply Terraform

Run local static validation:

```bash
terraform -chdir=infra/live/production fmt -check -recursive
terraform -chdir=infra/live/production init -backend=false
terraform -chdir=infra/live/production validate
```

Use the established remote-state production workflow for the plan. Review that it adds only:

- roles `tf3-production-operator` and `tf3-production-readonly`;
- two assume-role policies;
- five assume-role user-policy attachments;
- four `IAMUserChangePassword` attachments for individual users;
- two EKS access entries mapped to `tf3-production-operators` and `tf3-production-readers`.

Abort if the plan removes or replaces EKS resources, changes nodes/workloads, changes the existing administrator entry, manages access keys/passwords, or contains unrelated resources. Apply only the reviewed saved plan through the production workflow.

## Phase 4: Configure local role profiles

Each recipient configures their own source profile interactively with `aws configure --profile <username>`; never paste credentials into a command argument. Add a role profile to `~/.aws/config` using the relevant source profile:

```ini
[profile tf3-operator]
role_arn = arn:aws:iam::197826770971:role/tf3-production-operator
source_profile = cdo01-pm
region = ap-southeast-1

[profile tf3-readonly]
role_arn = arn:aws:iam::197826770971:role/tf3-production-readonly
source_profile = tf3-members-readonly
region = ap-southeast-1
```

Each operator substitutes their own source profile. Passwords are for console login only and are never written to AWS CLI profile files.

## Phase 5: Authorization verification

Use real assumed-role credentials and `kubectl auth can-i`. Operator positive checks include listing pods/logs, port-forward, Deployment scale/patch, Rollout patch, and reading NetworkPolicies. Operator denials must include:

```bash
kubectl auth can-i get secrets -n techx-tf3
kubectl auth can-i create pods --subresource=exec -n techx-tf3
kubectl auth can-i patch networkpolicies.networking.k8s.io -n techx-tf3
kubectl auth can-i patch statefulsets.apps -n techx-tf3
kubectl auth can-i delete persistentvolumeclaims -n techx-tf3
kubectl auth can-i create rolebindings.rbac.authorization.k8s.io -n techx-tf3
kubectl auth can-i patch applications.argoproj.io -n argocd
```

Every command above must return `no`. The reader must be able to list non-secret operational resources, read logs/metrics, and port-forward, while all mutation, Secret/ConfigMap read, exec, and other-namespace access return `no`. Prefer authorization checks; do not mutate a production object merely to prove access.

## Phase 6: Customer and control-plane verification

After apply, require:

- Argo applications remain `Synced/Healthy`;
- storefront and product smoke probes pass;
- Checkout `PlaceOrder`, browse, and cart queries contain non-zero traffic and meet SLO;
- frontend p95 remains below its threshold;
- no application pod restarted because of the access change.

If any gate fails, disable the new EKS access entries, revert the GitOps RBAC commit, and detach the source-user policies. Preserve `cdo-2-admin-team` and Argo CD authority throughout rollback.

## Credential distribution and deletion

Distribute each individual credential record out of band only to its owner. Distribute the shared read-only record only to approved members. Confirm receipt, then delete the handoff file and its private directory without displaying their contents. Record only who received access and when deletion occurred.

## Rotation and offboarding

- Rotate each individual access key at least every 90 days: create the replacement, verify assume-role, disable the old key, observe, then delete it. Never leave two active keys after rotation.
- Rotate the shared read-only key and password immediately whenever membership changes or exposure is suspected; redistribute out of band.
- Offboard an individual by disabling/deleting only that user's key and login profile, then detaching only that user's policies. Do not rotate or interrupt the other three operators.
- For suspected compromise, disable the affected key first, inspect CloudTrail, then rotate credentials and document the incident.
