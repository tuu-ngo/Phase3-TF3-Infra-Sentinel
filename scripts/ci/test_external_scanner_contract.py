from pathlib import Path


WORKFLOW = Path(".github/workflows/scan-external-images.yml").read_text()


def test_external_scanner_uses_catalog_as_its_only_image_source():
    assert "read-external-image-catalog.py" in WORKFLOW
    assert "external-image-allowlist.yaml" in WORKFLOW
    assert "EXTERNAL_IMAGES" not in WORKFLOW
    assert "postgres@sha256" not in WORKFLOW
    assert "valkey@sha256" not in WORKFLOW
