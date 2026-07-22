import base64
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path("scripts/ci/get-sbom.py")
SPEC = importlib.util.spec_from_file_location("get_sbom", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

PARENT = "sha256:" + "a" * 64
CHILD = "sha256:" + "b" * 64
ARM_CHILD = "sha256:" + "d" * 64
SOURCE = "c" * 40


def statement(**overrides):
    predicate = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "metadata": {
            "properties": [
                {"name": "techx.image", "value": MODULE.EXPECTED_REPOSITORY + "@" + CHILD},
                {"name": "techx.indexDigest", "value": PARENT},
                {"name": "techx.platform", "value": "linux/amd64"},
                {"name": "techx.sourceSha", "value": SOURCE},
                {"name": "techx.subjectDigest", "value": CHILD},
            ]
        },
        "components": [{"type": "library", "name": "example", "version": "1.0.0"}],
    }
    predicate.update(overrides)
    document = {
        "_type": "https://in-toto.io/Statement/v1",
        "predicateType": MODULE.CYCLONEDX_PREDICATE,
        "subject": [{"name": "example", "digest": {"sha256": CHILD.removeprefix("sha256:")}}],
        "predicate": predicate,
    }
    payload = base64.b64encode(json.dumps(document).encode()).decode()
    return {"payload": payload}


def select(entries, platform="linux/amd64"):
    return MODULE.select_sbom(
        entries,
        child_digest=CHILD,
        expected_index_digest=PARENT,
        expected_platform=platform,
    )


def test_selects_valid_sbom_and_validates_subject_and_properties():
    result = select([statement()])
    assert result["bomFormat"] == "CycloneDX"


def test_retrieve_selects_amd64_from_two_platform_index(monkeypatch):
    image = MODULE.EXPECTED_REPOSITORY + "@" + PARENT
    manifest = {
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": [
            {
                "digest": CHILD,
                "platform": {"os": "linux", "architecture": "amd64"},
            },
            {
                "digest": ARM_CHILD,
                "platform": {"os": "linux", "architecture": "arm64", "variant": "v8"},
            },
        ],
    }
    monkeypatch.setattr(MODULE, "manifest_for", lambda requested: manifest)
    monkeypatch.setattr(
        MODULE,
        "run_capture",
        lambda command, input_text=None: json.dumps([statement()]),
    )

    result = MODULE.retrieve(image, "linux/amd64", "ap-southeast-1", login=False)

    assert result["indexDigest"] == PARENT
    assert result["childDigest"] == CHILD
    assert result["platform"] == "linux/amd64"


def test_rejects_wrong_predicate_type():
    entry = statement()
    decoded = json.loads(base64.b64decode(entry["payload"]))
    decoded["predicateType"] = "https://example.test/wrong"
    entry["payload"] = base64.b64encode(json.dumps(decoded).encode()).decode()
    with pytest.raises(ValueError, match="no valid current"):
        select([entry])


def test_rejects_empty_sbom():
    entry = statement(components=[])
    with pytest.raises(ValueError, match="components must be non-empty"):
        select([entry])


def test_rejects_wrong_subject_digest():
    entry = statement()
    decoded = json.loads(base64.b64decode(entry["payload"]))
    decoded["subject"][0]["digest"]["sha256"] = "d" * 64
    entry["payload"] = base64.b64encode(json.dumps(decoded).encode()).decode()
    with pytest.raises(ValueError, match="no valid current"):
        select([entry])


def test_rejects_wrong_index_digest():
    entry = statement()
    decoded = json.loads(base64.b64decode(entry["payload"]))
    for item in decoded["predicate"]["metadata"]["properties"]:
        if item["name"] == "techx.indexDigest":
            item["value"] = "sha256:" + "d" * 64
    entry["payload"] = base64.b64encode(json.dumps(decoded).encode()).decode()
    with pytest.raises(ValueError, match="no valid current"):
        select([entry])


def test_rejects_ambiguous_valid_attestations():
    with pytest.raises(ValueError, match="ambiguous"):
        select([statement(), statement()])


def test_cosign_command_contains_exact_identity_and_issuer():
    command = MODULE.cosign_verify_command(MODULE.EXPECTED_REPOSITORY + "@" + CHILD)
    assert "--certificate-oidc-issuer" in command
    assert MODULE.EXPECTED_ISSUER in command
    assert "--certificate-identity" in command
    assert MODULE.EXPECTED_IDENTITY in command
