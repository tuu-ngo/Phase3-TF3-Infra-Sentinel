from pathlib import Path

import yaml


REPO = Path(__file__).resolve().parents[2]
ROLE_ARN = "arn:aws:iam::197826770971:role/techx-corp-tf3-kyverno-ecr"


def load_yaml(path):
    return yaml.safe_load((REPO / path).read_text())


def test_kyverno_controller_is_gitops_managed_and_version_pinned():
    application = load_yaml("gitops/apps/kyverno-app.yaml")
    assert application["kind"] == "Application"
    assert application["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"] == "10"
    assert application["spec"]["source"]["chart"] == "kyverno"
    assert application["spec"]["source"]["targetRevision"] == "3.3.4"
    assert application["spec"]["destination"]["namespace"] == "kyverno"
    assert application["spec"]["syncPolicy"]["automated"] == {
        "prune": True,
        "selfHeal": True,
    }
    assert "ServerSideApply=true" in application["spec"]["syncPolicy"]["syncOptions"]


def test_only_registry_verifier_controllers_receive_irsa():
    application = load_yaml("gitops/apps/kyverno-app.yaml")
    values = yaml.safe_load(application["spec"]["source"]["helm"]["values"])
    assert values["admissionController"]["rbac"]["serviceAccount"]["annotations"] == {
        "eks.amazonaws.com/role-arn": ROLE_ARN
    }
    assert values["backgroundController"]["rbac"]["serviceAccount"]["annotations"] == {
        "eks.amazonaws.com/role-arn": ROLE_ARN
    }
    assert "rbac" not in values["cleanupController"]
    assert "rbac" not in values["reportsController"]


def test_native_mandate05_enforcement_remains_present():
    native = REPO / "gitops/policies/native/mandate-05-runtime-policy.yaml"
    assert native.exists()
    documents = [document for document in yaml.safe_load_all(native.read_text()) if document]
    bindings = [document for document in documents if document["kind"] == "ValidatingAdmissionPolicyBinding"]
    assert len(bindings) == 2
    assert all(binding["spec"]["validationActions"] == ["Deny"] for binding in bindings)
