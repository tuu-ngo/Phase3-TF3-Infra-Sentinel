import json
import subprocess
from pathlib import Path


SCRIPT = Path("scripts/ci/verify-external-image-allowlist.py")
REPOSITORY = "197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp"
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


def run_verifier(tmp_path, allowlist):
    rendered = tmp_path / "rendered.yaml"
    catalog = tmp_path / "allowlist.yaml"
    output = tmp_path / "result.json"
    rendered.write_text(
        f"""
apiVersion: v1
kind: Pod
metadata:
  name: sample
  namespace: techx-tf3
spec:
  initContainers:
  - name: init
    image: init.example/image@{DIGEST_A}
  containers:
  - name: app
    image: {REPOSITORY}@{DIGEST_B}
  ephemeralContainers:
  - name: debug
    image: debug.example/image@{DIGEST_A}
"""
    )
    catalog.write_text(json_to_yaml(allowlist))
    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--rendered",
            str(rendered),
            "--allowlist",
            str(catalog),
            "--first-party-repository",
            REPOSITORY,
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    return result, json.loads(output.read_text()) if output.exists() else None


def json_to_yaml(document):
    import yaml

    return yaml.safe_dump(document, sort_keys=False)


def catalog(images):
    return {
        "schemaVersion": 1,
        "firstPartyRepository": REPOSITORY,
        "images": [{"image": image} for image in images],
    }


def test_allowlist_must_match_all_container_types(tmp_path):
    result, output = run_verifier(
        tmp_path,
        catalog(
            [
                f"debug.example/image@{DIGEST_A}",
                f"init.example/image@{DIGEST_A}",
            ]
        ),
    )
    assert result.returncode == 0, result.stderr
    assert output["externalImageCount"] == 2


def test_allowlist_rejects_missing_rendered_image(tmp_path):
    result, output = run_verifier(tmp_path, catalog([f"init.example/image@{DIGEST_A}"]))
    assert result.returncode != 0
    assert output is None
    assert "set mismatch" in result.stderr


def test_allowlist_rejects_tag_and_first_party_entries(tmp_path):
    result, output = run_verifier(
        tmp_path,
        catalog(
            [
                "debug.example/image:latest",
                f"init.example/image@{DIGEST_A}",
                f"{REPOSITORY}@{DIGEST_B}",
            ]
        ),
    )
    assert result.returncode != 0
    assert output is None
    assert "exact digest" in result.stderr or "first-party" in result.stderr
