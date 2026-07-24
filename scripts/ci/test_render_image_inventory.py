import json
import subprocess
from pathlib import Path


SCRIPT = Path("scripts/ci/render-image-inventory.py")
REPOSITORY = "197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp"


def run_inventory(tmp_path, rendered):
    rendered_path = tmp_path / "rendered.yaml"
    output_path = tmp_path / "inventory.json"
    rendered_path.write_text(rendered)
    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--rendered",
            str(rendered_path),
            "--first-party-repository",
            REPOSITORY,
            "--output",
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )
    return result, json.loads(output_path.read_text()) if output_path.exists() else None


def test_inventory_covers_workload_init_ephemeral_and_cronjob(tmp_path):
    rendered = f"""
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout
  namespace: techx-tf3
spec:
  template:
    spec:
      initContainers:
      - name: wait
        image: busybox@sha256:{'a' * 64}
      containers:
      - name: app
        image: {REPOSITORY}@sha256:{'b' * 64}
      ephemeralContainers:
      - name: debug
        image: alpine:3.20
---
apiVersion: batch/v1
kind: CronJob
metadata:
  name: nightly
  namespace: techx-tf3
spec:
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: job
            image: postgres@sha256:{'c' * 64}
"""
    result, inventory = run_inventory(tmp_path, rendered)
    assert result.returncode == 0, result.stderr
    assert inventory["imageCount"] == 4
    assert inventory["externalImages"] == [
        "alpine:3.20",
        f"busybox@sha256:{'a' * 64}",
        f"postgres@sha256:{'c' * 64}",
    ]
    assert len(inventory["firstPartyImages"]) == 1
    assert {item["containerType"] for item in inventory["images"]} == {
        "containers",
        "initContainers",
        "ephemeralContainers",
    }


def test_inventory_rejects_container_without_image(tmp_path):
    result, inventory = run_inventory(
        tmp_path,
        """
apiVersion: v1
kind: Pod
metadata:
  name: broken
spec:
  containers:
  - name: app
""",
    )
    assert result.returncode != 0
    assert inventory is None
    assert "without an image" in result.stderr


def test_first_party_tag_is_reported_as_mutable(tmp_path):
    result, inventory = run_inventory(
        tmp_path,
        f"""
apiVersion: v1
kind: Pod
metadata:
  name: mutable
spec:
  containers:
  - name: app
    image: {REPOSITORY}:release
""",
    )
    assert result.returncode == 0, result.stderr
    assert inventory["images"][0]["firstParty"] is True
    assert inventory["images"][0]["immutableDigest"] is False
