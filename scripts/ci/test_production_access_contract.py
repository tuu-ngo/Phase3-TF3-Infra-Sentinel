from pathlib import Path

import yaml


RBAC_PATH = Path("gitops/infrastructure/rbac-production-access.yaml")


def documents():
    return [doc for doc in yaml.safe_load_all(RBAC_PATH.read_text()) if doc]


def rules_for(role_name):
    role = next(
        doc
        for doc in documents()
        if doc["kind"] == "Role" and doc["metadata"]["name"] == role_name
    )
    return role["rules"]


def granted(role_name, resource, verb):
    return any(
        resource in rule.get("resources", []) and verb in rule.get("verbs", [])
        for rule in rules_for(role_name)
    )


def test_operator_excludes_security_sensitive_mutation():
    for resource in (
        "secrets",
        "networkpolicies",
        "persistentvolumeclaims",
        "roles",
        "rolebindings",
        "statefulsets",
    ):
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


def test_bindings_target_expected_groups_and_namespace():
    docs = documents()
    assert all(doc["metadata"]["namespace"] == "techx-tf3" for doc in docs)
    bindings = {doc["metadata"]["name"]: doc for doc in docs if doc["kind"] == "RoleBinding"}
    assert bindings["tf3-production-operator"]["subjects"][0]["name"] == "tf3-production-operators"
    assert bindings["tf3-production-readonly"]["subjects"][0]["name"] == "tf3-production-readers"


def test_terraform_declares_expected_roles_and_users():
    text = Path("infra/live/production/iam-production-access.tf").read_text()
    for name in ("cdo01-pm", "cdo01-tl", "cdo02-pm", "cdo02-tl", "tf3-members-readonly"):
        assert name in text
    assert 'name = "tf3-production-operator"' in text
    assert 'name = "tf3-production-readonly"' in text
    assert "AmazonEKSClusterAdminPolicy" not in text
    assert "aws_iam_access_key" not in text
    assert "aws:MultiFactorAuthPresent" not in text


def test_eks_group_mapping_keeps_existing_admin_path():
    text = Path("infra/modules/eks-platform/main.tf").read_text()
    assert "var.eks_admin_principal_arns" in text
    assert "var.eks_kubernetes_group_principals" in text
    assert "kubernetes_groups" in text


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
