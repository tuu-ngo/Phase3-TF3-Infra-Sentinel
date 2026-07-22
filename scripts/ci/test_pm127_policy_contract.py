from pathlib import Path

import yaml


REPO = Path(__file__).resolve().parents[2]
FIRST_PARTY = "197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp"
WORKFLOW_IDENTITY = (
    "https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel/"
    ".github/workflows/build-push-ecr.yml@refs/heads/main"
)


def load(path):
    return yaml.safe_load((REPO / path).read_text())


def test_first_party_policy_is_audit_and_requires_exact_signature_and_sbom():
    policy = load("gitops/policies/kyverno/verify-first-party-signatures.yaml")
    assert policy["spec"]["validationFailureAction"] == "Audit"
    assert policy["spec"]["background"] is True
    verify = policy["spec"]["rules"][0]["verifyImages"][0]
    assert verify["imageReferences"] == [FIRST_PARTY + "@sha256:*"]
    assert verify["required"] is True
    assert verify["mutateDigest"] is False
    assert verify["verifyDigest"] is True
    assert verify["imageRegistryCredentials"]["providers"] == ["amazon"]
    keyless = verify["attestors"][0]["entries"][0]["keyless"]
    assert keyless["issuer"] == "https://token.actions.githubusercontent.com"
    assert keyless["subject"] == WORKFLOW_IDENTITY
    attestation = verify["attestations"][0]
    assert attestation["predicateType"] == "https://cyclonedx.org/bom"
    attestor = attestation["attestors"][0]["entries"][0]["keyless"]
    assert attestor["issuer"] == "https://token.actions.githubusercontent.com"
    assert attestor["subject"] == WORKFLOW_IDENTITY


def test_external_policy_catalog_is_exactly_the_reviewed_catalog():
    policy = load("gitops/policies/kyverno/allow-approved-external-image-digests.yaml")
    catalog = load("docs/evidence/mandate-10/external-image-allowlist.yaml")
    expected = {entry["image"] for entry in catalog["images"]}
    assert policy["spec"]["validationFailureAction"] == "Audit"
    assert policy["spec"]["background"] is True
    foreach = policy["spec"]["rules"][0]["validate"]["foreach"]
    assert len(foreach) == 3
    for loop in foreach:
        assert "request.object.spec." in loop["list"]
        values = set(loop["deny"]["conditions"]["any"][0]["value"])
        assert values == expected
        assert loop["preconditions"]["all"][0]["operator"] == "Equals"
        assert loop["preconditions"]["all"][0]["value"] is False


def test_policy_application_is_gitops_ordered_after_controller():
    controller = load("gitops/apps/kyverno-app.yaml")
    policies = load("gitops/apps/kyverno-policies-app.yaml")
    assert controller["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"] == "10"
    assert policies["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"] == "20"
    assert policies["spec"]["source"]["path"] == "gitops/policies/kyverno"
    assert "ServerSideApply=true" in policies["spec"]["syncPolicy"]["syncOptions"]
