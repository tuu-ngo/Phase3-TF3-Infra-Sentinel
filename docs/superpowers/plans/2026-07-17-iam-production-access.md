# IAM and EKS Production Access Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create four individually attributable production operator IAM users, one shared read-only IAM user, two shared assume roles, and least-privilege namespace RBAC without changing any customer workload.

**Architecture:** A bootstrap Python program creates IAM users, console login profiles, and one initial access key per user without exposing credentials to Terraform state or process arguments. Terraform owns shared IAM roles, source-user assume-role permissions, and EKS access entries that map the roles to Kubernetes groups; Argo CD owns namespaced Roles and RoleBindings in `techx-tf3`.

**Tech Stack:** Python 3, boto3, pytest, Terraform 1.15, AWS IAM, Amazon EKS access entries, Kubernetes RBAC, Argo CD

## Global Constraints

- Do not create an Argo CD `AppProject`.
- Do not remove or modify the existing `cdo-2-admin-team` cluster-admin entry.
- Create exactly one initial access key per approved IAM user; never grant the source key direct production permissions.
- Do not require MFA or constrain role session names.
- Never print, commit, log, or place generated passwords, access-key IDs, or secret access keys in command arguments or Terraform state.
- Do not grant operators Secret access, pod exec, RBAC mutation, NetworkPolicy mutation, PVC/PV mutation, StatefulSet mutation, Argo mutation, or cluster-scoped mutation.
- Do not grant the shared reader ConfigMap or Secret reads, pod exec, or any mutation.
- Do not mutate workloads merely to test authorization; prefer `kubectl auth can-i` and server-side dry-run.
- Do not alter `flagd`, `/flagservice`, Envoy fault injection, customer traffic, application pod templates, Services, NetworkPolicies, data stores, or edge routing.
- All durable Kubernetes RBAC changes flow through PR and Argo CD.
- The local credential handoff file must use mode `0600` and live outside the repository.

---

## File Map

- `scripts/access/bootstrap_iam_users.py`: idempotently creates the five IAM users, login profiles, and one initial access key per user, then writes credentials to a protected handoff file.
- `scripts/access/test_bootstrap_iam_users.py`: unit tests the bootstrap program with an in-memory fake IAM client.
- `scripts/access/requirements.txt`: pins boto3 for the bootstrap environment.
- `infra/live/production/iam-production-access.tf`: declares operator/read-only roles, trust policies, source-user assume-role policies, and role-to-EKS-module inputs.
- `infra/live/production/main.tf`: passes role-to-Kubernetes-group mappings into the EKS module.
- `infra/live/production/variables.tf`: exposes no password or secret inputs; only documents the access model where needed.
- `infra/modules/eks-platform/variables.tf`: accepts a map of IAM principal ARNs to Kubernetes groups.
- `infra/modules/eks-platform/main.tf`: merges existing cluster-admin entries with group-only EKS access entries.
- `gitops/infrastructure/rbac-production-access.yaml`: defines namespaced operator and read-only Roles and RoleBindings.
- `scripts/ci/test_production_access_contract.py`: verifies Terraform and RBAC security invariants without contacting production.
- `.github/workflows/validate-production-access.yml`: runs contract tests and Terraform validation for access changes.
- `docs/runbooks/production-access-onboarding.md`: documents secure bootstrap, distribution, role assumption, verification, rotation, and offboarding.

---

### Task 1: IAM User Bootstrap Program

**Files:**
- Create: `scripts/access/bootstrap_iam_users.py`
- Create: `scripts/access/test_bootstrap_iam_users.py`
- Create: `scripts/access/requirements.txt`

**Interfaces:**
- Consumes: boto3 IAM client methods `get_user`, `create_user`, `get_login_profile`, `create_login_profile`, `list_access_keys`, and `create_access_key`.
- Produces: `bootstrap_users(iam_client, account_alias: str, output_path: pathlib.Path, password_factory: Callable[[], str]) -> list[dict[str, str]]` and CLI exit status `0` on success.

- [ ] **Step 1: Write failing tests for identity and credential handling**

Create `scripts/access/test_bootstrap_iam_users.py` with tests that assert:

```python
from pathlib import Path
import stat

from bootstrap_iam_users import OPERATOR_USERS, READONLY_USER, bootstrap_users


class FakeIAM:
    def __init__(self):
        self.users = set()
        self.login_profiles = {}
        self.access_keys = {}

    def get_user(self, UserName):
        if UserName not in self.users:
            raise self.exceptions.NoSuchEntityException({}, "GetUser")
        return {"User": {"UserName": UserName}}

    def create_user(self, UserName, Tags):
        self.users.add(UserName)
        return {"User": {"UserName": UserName}}

    def get_login_profile(self, UserName):
        if UserName not in self.login_profiles:
            raise self.exceptions.NoSuchEntityException({}, "GetLoginProfile")
        return {"LoginProfile": {"UserName": UserName}}

    def create_login_profile(self, UserName, Password, PasswordResetRequired):
        self.login_profiles[UserName] = {
            "Password": Password,
            "PasswordResetRequired": PasswordResetRequired,
        }

    def list_access_keys(self, UserName):
        return {"AccessKeyMetadata": self.access_keys.get(UserName, [])}

    def create_access_key(self, UserName):
        key = {
            "UserName": UserName,
            "AccessKeyId": f"TESTKEY-{UserName}",
            "SecretAccessKey": f"secret-{UserName}",
            "Status": "Active",
        }
        self.access_keys.setdefault(UserName, []).append(key)
        return {"AccessKey": key}

    class exceptions:
        class NoSuchEntityException(Exception):
            pass


def test_bootstrap_creates_exact_users_and_protected_handoff(tmp_path: Path):
    iam = FakeIAM()
    output = tmp_path / "handoff.json"

    records = bootstrap_users(iam, "197826770971", output, lambda: "Strong-temp-Password-42!")

    assert OPERATOR_USERS == ("cdo01-pm", "cdo01-tl", "cdo02-pm", "cdo02-tl")
    assert READONLY_USER == "tf3-members-readonly"
    assert iam.users == {*OPERATOR_USERS, READONLY_USER}
    assert len(records) == 5
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert all(iam.login_profiles[name]["PasswordResetRequired"] for name in OPERATOR_USERS)
    assert iam.login_profiles[READONLY_USER]["PasswordResetRequired"] is False
    assert all(len(iam.access_keys[name]) == 1 for name in (*OPERATOR_USERS, READONLY_USER))
    assert all("AccessKeyId" in record and "SecretAccessKey" in record for record in records)


def test_bootstrap_refuses_to_overwrite_existing_handoff(tmp_path: Path):
    iam = FakeIAM()
    output = tmp_path / "handoff.json"
    output.write_text("existing", encoding="utf-8")

    try:
        bootstrap_users(iam, "197826770971", output, lambda: "Strong-temp-Password-42!")
    except FileExistsError:
        pass
    else:
        raise AssertionError("existing handoff must not be overwritten")
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
python -m pytest scripts/access/test_bootstrap_iam_users.py -q
```

Expected: FAIL during import because `bootstrap_iam_users.py` does not exist.

- [ ] **Step 3: Implement the minimal bootstrap program**

Implement constants, password generation, idempotent user creation, login-profile creation, access-key creation, `0600` file handling, and JSON output. The CLI must require an explicit output path outside the Git root and verify AWS account `197826770971` before mutation.

The implementation must use boto3 API calls directly so credentials never appear in process arguments. It must create an access key only when the user has no existing key, must refuse to create a second key, must never print credential records, and must not overwrite an existing handoff file.

Use this public interface:

```python
OPERATOR_USERS = ("cdo01-pm", "cdo01-tl", "cdo02-pm", "cdo02-tl")
READONLY_USER = "tf3-members-readonly"
EXPECTED_ACCOUNT = "197826770971"

def generate_password() -> str: ...

def bootstrap_users(
    iam_client,
    account_alias: str,
    output_path: pathlib.Path,
    password_factory: Callable[[], str] = generate_password,
) -> list[dict[str, str]]: ...

def main() -> int: ...
```

For users with an existing login profile, record `status: "existing-login-profile"` without generating or retrieving a password. For users with an existing access key, record `status: "existing-access-key-not-retrievable"` and do not create another key. Never reset an existing password or rotate an existing key automatically.

- [ ] **Step 4: Pin the bootstrap dependency**

Create `scripts/access/requirements.txt`:

```text
boto3==1.40.1
pytest==8.4.1
```

- [ ] **Step 5: Run bootstrap tests and verify GREEN**

Run:

```bash
python -m pytest scripts/access/test_bootstrap_iam_users.py -q
```

Expected: `2 passed` and no password appears in captured output.

- [ ] **Step 6: Commit the bootstrap slice**

```bash
git add scripts/access/bootstrap_iam_users.py scripts/access/test_bootstrap_iam_users.py scripts/access/requirements.txt
git commit -m "feat: add safe IAM user bootstrap"
```

---

### Task 2: Namespaced Kubernetes RBAC

**Files:**
- Create: `gitops/infrastructure/rbac-production-access.yaml`
- Create: `scripts/ci/test_production_access_contract.py`

**Interfaces:**
- Consumes: Kubernetes groups `tf3-production-operators` and `tf3-production-readers` from EKS access entries.
- Produces: Roles `tf3-production-operator` and `tf3-production-readonly`, plus matching RoleBindings in `techx-tf3`.

- [ ] **Step 1: Write failing RBAC contract tests**

Create `scripts/ci/test_production_access_contract.py`. Parse all YAML documents in `gitops/infrastructure/rbac-production-access.yaml` with `yaml.safe_load_all` and assert:

```python
from pathlib import Path
import yaml

RBAC_PATH = Path("gitops/infrastructure/rbac-production-access.yaml")


def documents():
    return [doc for doc in yaml.safe_load_all(RBAC_PATH.read_text()) if doc]


def rules_for(role_name):
    role = next(doc for doc in documents() if doc["kind"] == "Role" and doc["metadata"]["name"] == role_name)
    return role["rules"]


def granted(role_name, resource, verb):
    return any(resource in rule.get("resources", []) and verb in rule.get("verbs", []) for rule in rules_for(role_name))


def test_operator_excludes_security_sensitive_mutation():
    for resource in ("secrets", "networkpolicies", "persistentvolumeclaims", "roles", "rolebindings", "statefulsets"):
        assert not granted("tf3-production-operator", resource, "create")
        assert not granted("tf3-production-operator", resource, "patch")
        assert not granted("tf3-production-operator", resource, "delete")
    assert not granted("tf3-production-operator", "pods/exec", "create")


def test_reader_has_no_mutation_or_sensitive_reads():
    for rule in rules_for("tf3-production-readonly"):
        assert set(rule["verbs"]) <= {"get", "list", "watch", "create"}
        if "create" in rule["verbs"]:
            assert rule["resources"] == ["pods/portforward"]
    assert not granted("tf3-production-readonly", "secrets", "get")
    assert not granted("tf3-production-readonly", "configmaps", "get")
    assert not granted("tf3-production-readonly", "pods/exec", "create")


def test_bindings_target_expected_groups():
    bindings = {doc["metadata"]["name"]: doc for doc in documents() if doc["kind"] == "RoleBinding"}
    assert bindings["tf3-production-operator"]["subjects"][0]["name"] == "tf3-production-operators"
    assert bindings["tf3-production-readonly"]["subjects"][0]["name"] == "tf3-production-readers"
```

- [ ] **Step 2: Run RBAC contract tests and verify RED**

Run:

```bash
python -m pytest scripts/ci/test_production_access_contract.py -q
```

Expected: FAIL because `rbac-production-access.yaml` does not exist.

- [ ] **Step 3: Create the least-privilege Roles and RoleBindings**

Create `gitops/infrastructure/rbac-production-access.yaml` with namespace `techx-tf3` on every object.

Operator Role rules must include:

```yaml
- apiGroups: [""]
  resources: ["pods", "pods/status", "services", "endpoints", "events"]
  verbs: ["get", "list", "watch"]
- apiGroups: [""]
  resources: ["pods/log"]
  verbs: ["get"]
- apiGroups: [""]
  resources: ["pods/portforward"]
  verbs: ["create"]
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["delete"]
- apiGroups: [""]
  resources: ["configmaps"]
  verbs: ["get", "list", "watch", "create", "update", "patch"]
- apiGroups: ["apps"]
  resources: ["deployments", "replicasets", "statefulsets"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["apps"]
  resources: ["deployments"]
  verbs: ["create", "update", "patch"]
- apiGroups: ["apps"]
  resources: ["deployments/scale"]
  verbs: ["get", "update", "patch"]
- apiGroups: ["batch"]
  resources: ["jobs", "cronjobs"]
  verbs: ["get", "list", "watch", "create", "update", "patch"]
- apiGroups: ["autoscaling"]
  resources: ["horizontalpodautoscalers"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["policy"]
  resources: ["poddisruptionbudgets"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["networking.k8s.io"]
  resources: ["networkpolicies"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["discovery.k8s.io"]
  resources: ["endpointslices"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["argoproj.io"]
  resources: ["rollouts", "analysisruns"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["argoproj.io"]
  resources: ["rollouts"]
  verbs: ["update", "patch"]
- apiGroups: ["argoproj.io"]
  resources: ["rollouts/scale"]
  verbs: ["get", "update", "patch"]
- apiGroups: ["metrics.k8s.io"]
  resources: ["pods"]
  verbs: ["get", "list"]
```

Reader Role is the read-only subset, excluding ConfigMaps, pod delete, Deployments mutation, Jobs/CronJobs mutation, and Rollout mutation. It retains `create` only on `pods/portforward`.

- [ ] **Step 4: Run RBAC tests and verify GREEN**

Run:

```bash
python -m pytest scripts/ci/test_production_access_contract.py -q
```

Expected: all RBAC contract tests PASS.

- [ ] **Step 5: Render and validate YAML locally**

Run:

```bash
kubectl apply --dry-run=client -f gitops/infrastructure/rbac-production-access.yaml
```

Expected: four objects report `(dry run)` with no schema errors.

- [ ] **Step 6: Commit the RBAC slice**

```bash
git add gitops/infrastructure/rbac-production-access.yaml scripts/ci/test_production_access_contract.py
git commit -m "feat: add least-privilege production RBAC"
```

---

### Task 3: IAM Roles and EKS Group Mappings

**Files:**
- Create: `infra/live/production/iam-production-access.tf`
- Modify: `infra/live/production/main.tf`
- Modify: `infra/modules/eks-platform/variables.tf`
- Modify: `infra/modules/eks-platform/main.tf`
- Modify: `scripts/ci/test_production_access_contract.py`

**Interfaces:**
- Consumes: IAM usernames from Task 1 and Kubernetes group names from Task 2.
- Produces: role ARNs `aws_iam_role.tf3_production_operator.arn` and `aws_iam_role.tf3_production_readonly.arn`, plus module input `eks_kubernetes_group_principals: map(list(string))`.

- [ ] **Step 1: Add failing Terraform contract tests**

Extend `scripts/ci/test_production_access_contract.py` to assert:

```python
def test_terraform_declares_expected_roles_and_users():
    text = Path("infra/live/production/iam-production-access.tf").read_text()
    for name in ("cdo01-pm", "cdo01-tl", "cdo02-pm", "cdo02-tl", "tf3-members-readonly"):
        assert name in text
    assert 'name = "tf3-production-operator"' in text
    assert 'name = "tf3-production-readonly"' in text
    assert "AmazonEKSClusterAdminPolicy" not in text
    assert "aws_iam_access_key" not in text


def test_eks_group_mapping_keeps_existing_admin_path():
    text = Path("infra/modules/eks-platform/main.tf").read_text()
    assert "var.eks_admin_principal_arns" in text
    assert "var.eks_kubernetes_group_principals" in text
    assert "kubernetes_groups" in text
```

- [ ] **Step 2: Run contract tests and verify RED**

Run:

```bash
python -m pytest scripts/ci/test_production_access_contract.py -q
```

Expected: FAIL because `iam-production-access.tf` and the group mapping do not exist.

- [ ] **Step 3: Add the EKS module input**

Add to `infra/modules/eks-platform/variables.tf`:

```hcl
variable "eks_kubernetes_group_principals" {
  description = "IAM principal ARNs mapped to Kubernetes groups without an EKS cluster access policy."
  type        = map(list(string))
  default     = {}
}
```

Refactor `access_entries` in `infra/modules/eks-platform/main.tf` to merge the existing admin entries with group entries:

```hcl
access_entries = merge(
  {
    for arn in var.eks_admin_principal_arns : arn => {
      principal_arn = arn
      policy_associations = {
        admin = {
          policy_arn = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
          access_scope = { type = "cluster" }
        }
      }
    }
  },
  {
    for arn, groups in var.eks_kubernetes_group_principals : arn => {
      principal_arn     = arn
      kubernetes_groups = groups
    }
  }
)
```

- [ ] **Step 4: Declare IAM roles and source-user permissions**

Create `infra/live/production/iam-production-access.tf` with:

- locals containing the exact four operator usernames and shared reader username;
- role trust policies using account root as Principal plus `ArnEquals` on `aws:PrincipalArn` to the approved source-user ARNs;
- `aws_iam_role` resources named `tf3-production-operator` and `tf3-production-readonly`;
- one managed assume-role policy per target role;
- attachments of the operator policy to four users and reader policy to the shared user;
- `IAMUserChangePassword` attachment only for the four individual users;
- no access-key resource, password input, EKS cluster access policy, wildcard assume-role resource, or MFA condition.

The trust-condition pattern must be exact:

```hcl
Principal = { AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root" }
Condition = {
  ArnEquals = {
    "aws:PrincipalArn" = local.operator_user_arns
  }
}
```

- [ ] **Step 5: Pass role mappings into the EKS module**

Add to the `module "eks_platform"` call in `infra/live/production/main.tf`:

```hcl
eks_kubernetes_group_principals = {
  (aws_iam_role.tf3_production_operator.arn) = ["tf3-production-operators"]
  (aws_iam_role.tf3_production_readonly.arn) = ["tf3-production-readers"]
}
```

- [ ] **Step 6: Run tests and Terraform validation**

Run:

```bash
python -m pytest scripts/ci/test_production_access_contract.py -q
terraform -chdir=infra/live/production fmt -check -recursive
terraform -chdir=infra/live/production init -backend=false
terraform -chdir=infra/live/production validate
```

Expected: pytest PASS, formatting check exit `0`, init succeeds without backend access, and validation reports `Success! The configuration is valid.`

- [ ] **Step 7: Commit the Terraform slice**

```bash
git add infra/live/production/iam-production-access.tf infra/live/production/main.tf infra/modules/eks-platform/variables.tf infra/modules/eks-platform/main.tf scripts/ci/test_production_access_contract.py
git commit -m "feat: add shared production access roles"
```

---

### Task 4: CI Security Gate

**Files:**
- Create: `.github/workflows/validate-production-access.yml`
- Modify: `scripts/ci/test_production_access_contract.py`

**Interfaces:**
- Consumes: bootstrap program, RBAC manifest, and Terraform access declarations from Tasks 1-3.
- Produces: a required CI signal named `Validate production access`.

- [ ] **Step 1: Add a failing workflow contract test**

Extend `scripts/ci/test_production_access_contract.py`:

```python
def test_ci_workflow_covers_all_access_paths():
    text = Path(".github/workflows/validate-production-access.yml").read_text()
    for path in (
        "scripts/access/**",
        "scripts/ci/test_production_access_contract.py",
        "gitops/infrastructure/rbac-production-access.yaml",
        "infra/live/production/**",
        "infra/modules/eks-platform/**",
    ):
        assert path in text
    assert "terraform validate" in text
    assert "test_production_access_contract.py" in text
```

- [ ] **Step 2: Run the contract test and verify RED**

Run:

```bash
python -m pytest scripts/ci/test_production_access_contract.py -q
```

Expected: FAIL because the workflow does not exist.

- [ ] **Step 3: Create the workflow**

Create `.github/workflows/validate-production-access.yml` triggered on pull requests and pushes to `main` for the exact paths in the test. The job must:

1. check out the repository;
2. set up the repo-supported Python version;
3. install `PyYAML` and pytest without executing the bootstrap program;
4. run both Python test files;
5. set up the repo-supported Terraform version;
6. run `terraform fmt -check -recursive`;
7. run `terraform init -backend=false` and `terraform validate` in `infra/live/production`.

Do not configure AWS credentials and do not run Terraform plan/apply.

- [ ] **Step 4: Verify the workflow contract**

Run:

```bash
python -m pytest scripts/access/test_bootstrap_iam_users.py scripts/ci/test_production_access_contract.py -q
```

Expected: all tests PASS.

- [ ] **Step 5: Commit the CI slice**

```bash
git add .github/workflows/validate-production-access.yml scripts/ci/test_production_access_contract.py
git commit -m "ci: validate production access controls"
```

---

### Task 5: Access Runbook

**Files:**
- Create: `docs/runbooks/production-access-onboarding.md`
- Modify: `scripts/ci/test_production_access_contract.py`

**Interfaces:**
- Consumes: role names, usernames, Kubernetes groups, and bootstrap CLI from Tasks 1-4.
- Produces: operator procedure for bootstrap, plan/apply, password distribution, role assumption, verification, rotation, and offboarding.

- [ ] **Step 1: Add a failing runbook contract test**

Extend the contract test:

```python
def test_runbook_contains_safety_and_recovery_gates():
    text = Path("docs/runbooks/production-access-onboarding.md").read_text()
    for phrase in (
        "197826770971",
        "tf3-production-operator",
        "tf3-production-readonly",
        "one active access key per user",
        "do not remove cdo-2-admin-team",
        "kubectl auth can-i",
        "delete the handoff file",
        "Argo CD",
    ):
        assert phrase.lower() in text.lower()
```

- [ ] **Step 2: Run the contract test and verify RED**

Run:

```bash
python -m pytest scripts/ci/test_production_access_contract.py -q
```

Expected: FAIL because the runbook does not exist.

- [ ] **Step 3: Write the complete runbook**

Document exact safe phases:

1. verify AWS account `197826770971`;
2. render and merge GitOps RBAC first;
3. confirm Argo `Synced/Healthy` and no pod restart;
4. create `/tmp` handoff path with `mktemp`, then run the boto3 bootstrap without logging output;
5. run Terraform fmt/init/validate and a remote-state-backed plan through the production workflow;
6. review that the plan adds two roles, policy attachments, and two EKS access entries without changing the existing admin entry;
7. apply only the reviewed plan;
8. configure named AWS profiles for role assumption without writing passwords into profile files;
9. execute the full positive/negative `kubectl auth can-i` matrix;
10. verify storefront smoke and business SLOs;
11. distribute temporary passwords out of band;
12. delete the handoff file after distribution;
13. rotate the shared password on membership changes;
14. offboard one individual without affecting the other operators;
15. retain `cdo-2-admin-team` until a separate de-privileging change is approved.

Document 90-day individual key rotation and immediate shared-key rotation on membership change. Do not include example passwords, real credentials, secret values, or commands that echo the handoff file.

- [ ] **Step 4: Run all access tests**

Run:

```bash
python -m pytest scripts/access/test_bootstrap_iam_users.py scripts/ci/test_production_access_contract.py -q
```

Expected: all tests PASS.

- [ ] **Step 5: Commit the runbook slice**

```bash
git add docs/runbooks/production-access-onboarding.md scripts/ci/test_production_access_contract.py
git commit -m "docs: add production access onboarding runbook"
```

---

### Task 6: Pre-Production Verification and Controlled Execution

**Files:**
- Modify only if verification finds a defect in files created by Tasks 1-5.
- Local-only output: password handoff file under `/tmp`, Terraform plan artifact, and read-only verification logs; none are committed.

**Interfaces:**
- Consumes: all deliverables from Tasks 1-5 and explicit user approval for external IAM/Terraform mutations.
- Produces: five IAM users, two assumable roles, two EKS access entries, verified namespace authorization, and an evidence summary without credentials.

- [ ] **Step 1: Run the complete local verification suite**

Run:

```bash
python -m pytest scripts/access/test_bootstrap_iam_users.py scripts/ci/test_production_access_contract.py -q
terraform -chdir=infra/live/production fmt -check -recursive
terraform -chdir=infra/live/production init -backend=false
terraform -chdir=infra/live/production validate
kubectl apply --dry-run=client -f gitops/infrastructure/rbac-production-access.yaml
```

Expected: all tests PASS, Terraform configuration valid, and all four RBAC objects pass client-side dry-run.

- [ ] **Step 2: Review the complete diff and security invariants**

Run:

```bash
git diff origin/main...HEAD --check
git diff --stat origin/main...HEAD
git grep -n -E 'aws_iam_access_key|AmazonEKSClusterAdminPolicy|pods/exec|resources:.*secrets' -- scripts/access infra/live/production/iam-production-access.tf gitops/infrastructure/rbac-production-access.yaml
```

Expected:

- no Terraform-managed access-key resource (access keys are bootstrap-owned);
- `AmazonEKSClusterAdminPolicy` appears only in the pre-existing EKS admin mapping, not the new role declarations;
- no operator/reader grant for `pods/exec` or Secrets;
- no password-like value in the diff.

- [ ] **Step 3: Obtain explicit approval before external writes**

Present:

- exact IAM users to create;
- exact roles and EKS entries Terraform will add;
- exact RBAC permissions;
- confirmation that existing cluster-admin remains;
- handoff-file path policy;
- rollback sequence.

Do not proceed without explicit approval for IAM creation and Terraform apply.

- [ ] **Step 4: Merge RBAC through PR and verify Argo**

After approval and PR merge, observe only:

```bash
kubectl -n argocd get application techx-infrastructure-app
kubectl -n techx-tf3 get role,rolebinding | grep tf3-production
kubectl -n techx-tf3 get pods
```

Expected: Application `Synced/Healthy`, two Roles and two RoleBindings exist, and no application pod age/restart changes due to RBAC.

- [ ] **Step 5: Bootstrap IAM users without exposing passwords**

Create an output path using `mktemp` and run the bootstrap program with command output limited to usernames/status only. Verify file mode using `stat`; never display file contents.

Expected: five IAM users, five login profiles, exactly one active access key per user, and a `0600` handoff file.

- [ ] **Step 6: Run reviewed Terraform plan and apply**

Use the established production workflows. The plan must add only:

- two IAM roles;
- two assume-role policies and five user-policy attachments;
- four individual password-change policy attachments;
- two EKS access entries/group mappings.

Abort if the plan removes/replaces EKS, changes node groups, modifies the existing admin entry, or includes unrelated resources.

- [ ] **Step 7: Verify positive and negative authorization**

For operator assumed-role credentials, verify the matrix from the spec. For reader credentials, verify all mutation is denied. Use `kubectl auth can-i` first; use server-side dry-run only where impersonation cannot prove the full request path.

Expected: every positive case returns `yes`, every negative case returns `no`, and no production object changes.

- [ ] **Step 8: Verify customer health and remove temporary credential material**

Refresh live context and confirm:

- storefront and product smoke probes PASS;
- Checkout `PlaceOrder`, browse, and cart SLO queries contain non-zero traffic and meet thresholds;
- Argo applications remain `Synced/Healthy`;
- no pod restarted because of the access change.

After out-of-band distribution, securely delete the local handoff file and record only that deletion occurred, never its contents.

- [ ] **Step 9: Final review commit if verification required corrections**

If Tasks 6-8 required code corrections, commit only those reviewed corrections:

```bash
git add <exact corrected files>
git commit -m "fix: correct production access verification"
```

If no files changed, do not create an empty commit.

---

## Final Definition of Done

- Five IAM users exist with console login profiles and exactly one active access key each.
- Four individual users can assume only `tf3-production-operator`.
- The shared user can assume only `tf3-production-readonly`.
- Operator and reader permissions match the spec and all denial tests pass.
- Argo CD remains `Synced/Healthy` and no application pod restarts.
- Storefront smoke and business SLOs show no regression with non-zero traffic.
- Existing `cdo-2-admin-team` cluster-admin access remains unchanged.
- No AppProject, NetworkPolicy, workload, data-store, edge, flagd, or secret change is included.
- The password handoff file is mode `0600`, never printed or committed, and deleted after distribution.
