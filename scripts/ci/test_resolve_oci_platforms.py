import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path("scripts/ci/resolve-oci-platforms.py")
SPEC = importlib.util.spec_from_file_location("resolve_oci_platforms", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

PARENT = "sha256:" + "a" * 64
AMD64 = "sha256:" + "b" * 64
ARM64 = "sha256:" + "c" * 64
IMAGE = "example.test/techx-corp@" + PARENT


def index_document():
    return {
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": [
            {
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "digest": AMD64,
                "platform": {"os": "linux", "architecture": "amd64"},
            },
            {
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "digest": ARM64,
                "platform": {"os": "linux", "architecture": "arm64", "variant": "v8"},
            },
            {
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "digest": "sha256:" + "d" * 64,
                "platform": {"os": "unknown", "architecture": "unknown"},
            },
        ],
    }


def test_resolve_index_maps_each_expected_platform_to_child_digest():
    result = MODULE.resolve(index_document(), IMAGE, ["linux/amd64", "linux/arm64"])
    assert result["indexDigest"] == PARENT
    assert result["platforms"] == [
        {
            "platform": "linux/amd64",
            "digest": AMD64,
            "image": "example.test/techx-corp@" + AMD64,
        },
        {
            "platform": "linux/arm64",
            "digest": ARM64,
            "image": "example.test/techx-corp@" + ARM64,
        },
    ]


def test_resolve_accepts_docker_manifest_list():
    document = index_document()
    document["mediaType"] = "application/vnd.docker.distribution.manifest.list.v2+json"
    result = MODULE.resolve(document, IMAGE, ["linux/amd64", "linux/arm64"])
    assert result["platforms"][1]["digest"] == ARM64


def test_resolve_single_manifest_uses_parent_digest():
    document = {"mediaType": "application/vnd.oci.image.manifest.v1+json"}
    result = MODULE.resolve(document, IMAGE, ["linux/amd64"])
    assert result["platforms"] == [
        {"platform": "linux/amd64", "digest": PARENT, "image": IMAGE}
    ]


def test_resolve_rejects_missing_platform():
    document = index_document()
    document["manifests"] = [document["manifests"][0], document["manifests"][2]]
    with pytest.raises(ValueError, match="missing child digest for linux/arm64"):
        MODULE.resolve(document, IMAGE, ["linux/amd64", "linux/arm64"])


def test_resolve_rejects_duplicate_platform_descriptor():
    document = index_document()
    document["manifests"].append(document["manifests"][0].copy())
    with pytest.raises(ValueError, match="ambiguous child digests for linux/amd64"):
        MODULE.resolve(document, IMAGE, ["linux/amd64", "linux/arm64"])


def test_resolve_rejects_unexpected_runnable_platform():
    document = index_document()
    document["manifests"].append(
        {
            "digest": "sha256:" + "e" * 64,
            "platform": {"os": "linux", "architecture": "s390x"},
        }
    )
    with pytest.raises(ValueError, match="unexpected runnable platforms: linux/s390x"):
        MODULE.resolve(document, IMAGE, ["linux/amd64", "linux/arm64"])


def test_resolve_rejects_tag_reference():
    with pytest.raises(ValueError, match="immutable"):
        MODULE.resolve(index_document(), "example.test/techx-corp:latest", ["linux/amd64"])
