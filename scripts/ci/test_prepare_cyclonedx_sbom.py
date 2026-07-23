import json
import subprocess
from pathlib import Path


SCRIPT = Path("scripts/ci/prepare-cyclonedx-sbom.py")
DIGEST = "sha256:" + "a" * 64
SOURCE_SHA = "b" * 40


def run_prepare(tmp_path, document, **overrides):
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "output.json"
    input_path.write_text(json.dumps(document))
    args = {
        "image": "197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp@" + DIGEST,
        "platform": "linux/amd64",
        "index_digest": DIGEST,
        "subject_digest": DIGEST,
        "source_sha": SOURCE_SHA,
    }
    args.update(overrides)
    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            *[
                item
                for key, value in args.items()
                for item in (f"--{key.replace('_', '-')}", value)
            ],
        ],
        capture_output=True,
        text=True,
    )
    return result, json.loads(output_path.read_text()) if output_path.exists() else None


def valid_sbom():
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": "urn:uuid:00000000-0000-0000-0000-000000000000",
        "metadata": {"timestamp": "2026-07-22T00:00:00Z", "properties": []},
        "components": [{"type": "library", "name": "example", "version": "1.0.0"}],
    }


def test_prepare_adds_subject_binding_properties(tmp_path):
    result, output = run_prepare(tmp_path, valid_sbom())
    assert result.returncode == 0, result.stderr
    properties = {item["name"]: item["value"] for item in output["metadata"]["properties"]}
    assert properties == {
        "techx.image": "197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp@" + DIGEST,
        "techx.indexDigest": DIGEST,
        "techx.platform": "linux/amd64",
        "techx.sourceSha": SOURCE_SHA,
        "techx.subjectDigest": DIGEST,
    }


def test_prepare_rejects_non_cyclonedx(tmp_path):
    document = valid_sbom()
    document["bomFormat"] = "SPDX"
    result, output = run_prepare(tmp_path, document)
    assert result.returncode != 0
    assert output is None
    assert "CycloneDX" in result.stderr


def test_prepare_rejects_empty_components(tmp_path):
    document = valid_sbom()
    document["components"] = []
    result, output = run_prepare(tmp_path, document)
    assert result.returncode != 0
    assert output is None
    assert "meaningful component" in result.stderr


def test_prepare_rejects_component_without_name(tmp_path):
    document = valid_sbom()
    document["components"] = [{"type": "library", "name": "  "}]
    result, output = run_prepare(tmp_path, document)
    assert result.returncode != 0
    assert output is None
    assert "non-empty name" in result.stderr


def test_prepare_rejects_component_without_type(tmp_path):
    document = valid_sbom()
    document["components"] = [{"name": "example"}]
    result, output = run_prepare(tmp_path, document)
    assert result.returncode != 0
    assert output is None
    assert "non-empty type" in result.stderr


def test_prepare_rejects_digest_binding_mismatch(tmp_path):
    result, output = run_prepare(tmp_path, valid_sbom(), subject_digest="sha256:" + "c" * 63)
    assert result.returncode != 0
    assert output is None
    assert "lowercase sha256" in result.stderr


def test_prepare_rejects_invalid_index_digest(tmp_path):
    result, output = run_prepare(tmp_path, valid_sbom(), index_digest="sha256:" + "c" * 63)
    assert result.returncode != 0
    assert output is None
    assert "index digest" in result.stderr


def test_prepare_rejects_reserved_property_replacement(tmp_path):
    document = valid_sbom()
    document["metadata"]["properties"] = [{"name": "techx.subjectDigest", "value": "wrong"}]
    result, output = run_prepare(tmp_path, document)
    assert result.returncode != 0
    assert output is None
    assert "reserved TechX property" in result.stderr


def test_prepare_rejects_invalid_source_sha(tmp_path):
    result, output = run_prepare(tmp_path, valid_sbom(), source_sha="not-a-sha")
    assert result.returncode != 0
    assert output is None
    assert "source SHA" in result.stderr
