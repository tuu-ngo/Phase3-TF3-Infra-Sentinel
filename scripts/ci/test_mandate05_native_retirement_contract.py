from pathlib import Path

import yaml


REPO = Path(__file__).resolve().parents[2]


def load_documents(relative_path: str) -> list[dict]:
    with (REPO / relative_path).open(encoding="utf-8") as stream:
        return [document for document in yaml.safe_load_all(stream) if document]


def named_documents(relative_path: str) -> dict[str, dict]:
    return {
        document["metadata"]["name"]: document
        for document in load_documents(relative_path)
    }


def test_native_vap_bindings_remain_deny_and_exclude_only_kube_system():
    documents = named_documents("gitops/policies/native/mandate-05-runtime-policy.yaml")
    expected = {
        "mandate05-native-resource-requirements-techx-tf3",
        "mandate05-native-image-reference-techx-tf3",
    }

    for name in expected:
        binding = documents[name]
        assert binding["kind"] == "ValidatingAdmissionPolicyBinding"
        assert binding["spec"]["validationActions"] == ["Deny"]
        expressions = binding["spec"]["matchResources"]["namespaceSelector"][
            "matchExpressions"
        ]
        assert expressions == [
            {
                "key": "kubernetes.io/metadata.name",
                "operator": "NotIn",
                "values": ["kube-system"],
            }
        ]


def test_psa_enforcement_and_observability_exception_are_explicit():
    techx = load_documents("gitops/infrastructure/namespace-techx-tf3.yaml")[0]
    techx_labels = techx["metadata"]["labels"]
    assert techx_labels["pod-security.kubernetes.io/enforce"] == "restricted"
    assert techx_labels["pod-security.kubernetes.io/enforce-version"] == "v1.35"

    observability = load_documents(
        "gitops/infrastructure/namespace-observability-system.yaml"
    )[0]
    observability_labels = observability["metadata"]["labels"]
    assert "pod-security.kubernetes.io/enforce" not in observability_labels
    assert observability_labels["pod-security.kubernetes.io/warn"] == "baseline"
    assert observability_labels["pod-security.kubernetes.io/audit"] == "baseline"


def test_kyverno_is_absent_from_gitops_desired_state():
    assert not (REPO / "gitops/apps/kyverno-app.yaml").exists()
    assert not (REPO / "gitops/apps/kyverno-policies-app.yaml").exists()
    assert not (REPO / "gitops/policies/kyverno").exists()


def test_argocd_self_uses_server_side_apply():
    application = load_documents("gitops/apps/argocd-self-app.yaml")[0]
    sync_options = application["spec"]["syncPolicy"]["syncOptions"]
    assert "ServerSideApply=true" in sync_options
