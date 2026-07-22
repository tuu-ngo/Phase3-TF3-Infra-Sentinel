from pathlib import Path


WORKFLOW = Path(".github/workflows/build-push-ecr.yml").read_text()


def test_workflow_generates_and_verifies_platform_sbom_attestations():
    assert "Generate, attest, and verify CycloneDX SBOMs" in WORKFLOW
    assert "--format cyclonedx" in WORKFLOW
    assert "--platform \"$platform\"" in WORKFLOW
    assert "prepare-cyclonedx-sbom.py" in WORKFLOW
    assert "cosign attest" in WORKFLOW
    assert "cosign verify-attestation" in WORKFLOW
    assert "--type cyclonedx" in WORKFLOW
    assert "--subject-digest \"$digest\"" in WORKFLOW
    assert "--source-sha \"$SOURCE_SHA\"" in WORKFLOW


def test_workflow_uses_exact_github_oidc_identity_for_sbom():
    assert 'EXPECTED_IDENTITY="https://github.com/${GITHUB_WORKFLOW_REF}"' in WORKFLOW
    assert "--certificate-oidc-issuer https://token.actions.githubusercontent.com" in WORKFLOW
    assert 'predicateType: "https://cyclonedx.org/bom"' in WORKFLOW
    assert "sbom-index.json" in WORKFLOW


def test_sbom_generation_precedes_release_evidence_upload():
    generation = WORKFLOW.index("Generate, attest, and verify CycloneDX SBOMs")
    upload = WORKFLOW.index("Upload signed release evidence")
    assert generation < upload


def test_workflow_does_not_allow_pending_sbom_or_skip_attestation():
    assert "allow-pending-sbom" not in WORKFLOW
    assert "if-no-files-found: warn" in WORKFLOW
    assert "if-no-files-found: error" in WORKFLOW
