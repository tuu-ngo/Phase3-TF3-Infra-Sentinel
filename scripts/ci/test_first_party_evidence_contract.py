from pathlib import Path


SCRIPT = Path("scripts/ci/verify-first-party-evidence.sh").read_text()


def test_evidence_matrix_verifies_standalone_signatures_and_sboms_separately():
    assert 'cosign verify \\' in SCRIPT
    assert '"$GET_SBOM" "$VALID_IMAGE" --platform linux/amd64 --metadata' in SCRIPT
    assert "unsigned-signature" in SCRIPT
    assert "wrong-issuer-signature" in SCRIPT
    assert "wrong-identity-signature" in SCRIPT
    assert '"$MISSING_SBOM_IMAGE" > "$tmpdir/missing-sbom-signature.json"' in SCRIPT
    assert '"$WRONG_PREDICATE_IMAGE" > "$tmpdir/wrong-predicate-signature.json"' in SCRIPT
