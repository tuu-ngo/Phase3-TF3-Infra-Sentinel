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
    assert application["spec"]["source"]["targetRevision"] == "3.8.2"
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
    assert values["reportsController"]["rbac"]["serviceAccount"]["annotations"] == {
        "eks.amazonaws.com/role-arn": ROLE_ARN
    }
    assert "rbac" not in values["backgroundController"]
    assert "rbac" not in values["cleanupController"]


def test_admission_and_reports_controllers_are_ha_and_immutable():
    application = load_yaml("gitops/apps/kyverno-app.yaml")
    values = yaml.safe_load(application["spec"]["source"]["helm"]["values"])
    assert values["admissionController"]["replicas"] == 3
    assert values["admissionController"]["podDisruptionBudget"] == {
        "enabled": True,
        "minAvailable": 2,
    }
    assert values["reportsController"]["replicas"] == 2
    assert values["reportsController"]["podDisruptionBudget"] == {
        "enabled": True,
        "minAvailable": 1,
    }
    assert values["admissionController"]["container"]["image"]["tag"].startswith("v1.18.2@sha256:")
    assert values["admissionController"]["initContainer"]["image"]["tag"].startswith("v1.18.2@sha256:")
    assert values["reportsController"]["image"]["tag"].startswith("v1.18.2@sha256:")
    assert values["backgroundController"]["image"]["tag"].startswith("v1.18.2@sha256:")
    assert values["cleanupController"]["image"]["tag"].startswith("v1.18.2@sha256:")
    assert values["crds"]["migration"]["image"]["tag"].startswith("v1.18.2@sha256:")
    assert values["webhooksCleanup"]["image"]["tag"].startswith("v1.18.2@sha256:")
    assert values["test"]["image"]["tag"].startswith("v1.18.2@sha256:")
    assert "bitnamilegacy" not in yaml.safe_dump(values)
    assert len(values["admissionController"]["topologySpreadConstraints"]) == 2
    assert len(values["reportsController"]["topologySpreadConstraints"]) == 2


def test_kyverno_image_catalog_matches_render_value_pins():
    application = load_yaml("gitops/apps/kyverno-app.yaml")
    values = yaml.safe_load(application["spec"]["source"]["helm"]["values"])
    catalog = load_yaml("docs/evidence/mandate-10/kyverno-image-allowlist.yaml")
    refs = {
        "reg.kyverno.io/kyverno/kyverno:v1.18.2@" + values["admissionController"]["container"]["image"]["tag"].split("@", 1)[1],
        "reg.kyverno.io/kyverno/kyvernopre:v1.18.2@" + values["admissionController"]["initContainer"]["image"]["tag"].split("@", 1)[1],
        "reg.kyverno.io/kyverno/background-controller:v1.18.2@" + values["backgroundController"]["image"]["tag"].split("@", 1)[1],
        "reg.kyverno.io/kyverno/reports-controller:v1.18.2@" + values["reportsController"]["image"]["tag"].split("@", 1)[1],
        "reg.kyverno.io/kyverno/cleanup-controller:v1.18.2@" + values["cleanupController"]["image"]["tag"].split("@", 1)[1],
        "reg.kyverno.io/kyverno/kyverno-cli:v1.18.2@" + values["crds"]["migration"]["image"]["tag"].split("@", 1)[1],
        "ghcr.io/kyverno/readiness-checker:v1.18.2@" + values["webhooksCleanup"]["image"]["tag"].split("@", 1)[1],
    }
    assert refs == {entry["image"] for entry in catalog["images"]}


def test_native_mandate05_enforcement_remains_present():
    native = REPO / "gitops/policies/native/mandate-05-runtime-policy.yaml"
    assert native.exists()
    documents = [document for document in yaml.safe_load_all(native.read_text()) if document]
    bindings = [document for document in documents if document["kind"] == "ValidatingAdmissionPolicyBinding"]
    assert len(bindings) == 2
    assert all(binding["spec"]["validationActions"] == ["Deny"] for binding in bindings)
