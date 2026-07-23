import subprocess
import sys
from pathlib import Path


SCRIPT = Path("scripts/ci/read-external-image-catalog.py")
CATALOG = Path("docs/evidence/mandate-10/external-image-allowlist.yaml")


def test_scan_input_is_derived_from_the_reviewed_catalog():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--allowlist", str(CATALOG)],
        capture_output=True,
        text=True,
        check=True,
    )
    images = result.stdout.splitlines()
    assert images == sorted(images)
    assert len(images) == 8
    assert any(image.startswith("busybox@sha256:") for image in images)
    assert any(image.startswith("quay.io/kiwigrid/k8s-sidecar:") for image in images)
    assert not any("postgres" in image for image in images)
    assert not any("valkey" in image for image in images)
