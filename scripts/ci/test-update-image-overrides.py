import os
import json
import shutil
import tempfile
import subprocess
from pathlib import Path

def setup_fixtures(temp_dir):
    values_content = """default:
  image:
    repository: repo
    tag: default-tag

components:
  ad:
    imageOverride:
      digest: sha256:old_ad
  product-catalog:
    # A comment
    imageOverride:
      digest: sha256:old_pc
      tag: old-product-catalog
  currency:
    replicas: 2
  unrelated:
    something: else
"""
    values_path = os.path.join(temp_dir, "values-prod.yaml")
    with open(values_path, "w") as f:
        f.write(values_content)

    manifest_content = {
        "schemaVersion": 1,
        "services": [
            {
                "name": "ad",
                "tag": "new-ad",
                "digest": "sha256:new_ad"
            },
            {
                "name": "product-catalog",
                "tag": "new-product-catalog",
                "digest": "sha256:new_pc"
            },
            {
                "name": "currency",
                "tag": "new-currency",
                "digest": "sha256:new_currency"
            },
            {
                "name": "flagd-ui",
                "tag": "new-flagd-ui",
                "digest": "sha256:new_flagd"
            }
        ]
    }
    manifest_path = os.path.join(temp_dir, "approved-images.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest_content, f)

    return values_path, manifest_path

def run_updater(values_path, manifest_path, summary_path, extra_args=[]):
    cmd = [
        "python3", "scripts/ci/update-image-overrides.py",
        "--values", values_path,
        "--manifest", manifest_path,
        "--summary-output", summary_path
    ] + extra_args
    return subprocess.run(cmd, capture_output=True, text=True)

def test_successful_update():
    with tempfile.TemporaryDirectory() as d:
        values, manifest = setup_fixtures(d)
        summary = os.path.join(d, "summary.json")
        
        res = run_updater(values, manifest, summary, ["--excluded-service", "flagd-ui"])
        assert res.returncode == 0, f"Failed: {res.stderr}"
        
        with open(values, "r") as f:
            new_yaml = f.read()

        assert "digest: sha256:new_ad" in new_yaml, "ad digest not updated"
        assert "tag: new-ad" not in new_yaml, "ad tag was added but it shouldn't be"

        assert "digest: sha256:new_pc" in new_yaml, "product-catalog digest not updated"
        assert "tag: new-product-catalog" in new_yaml, "product-catalog tag not updated"
        assert "# A comment" in new_yaml, "comment was lost"

        assert "digest: sha256:new_currency" in new_yaml, "currency digest not added"
        
        assert "flagd-ui" not in new_yaml, "flagd-ui was added but should be skipped"
        
        assert "something: else" in new_yaml, "unrelated component modified"
        assert "tag: default-tag" in new_yaml, "default tag was modified"

        # Idempotency
        res2 = run_updater(values, manifest, summary, ["--excluded-service", "flagd-ui"])
        assert res2.returncode == 0
        with open(values, "r") as f:
            new_yaml2 = f.read()
        assert new_yaml == new_yaml2, "Not idempotent"

def test_unknown_service():
    with tempfile.TemporaryDirectory() as d:
        values, manifest = setup_fixtures(d)
        summary = os.path.join(d, "summary.json")
        
        # Add unknown service
        with open(manifest, "r") as f:
            m = json.load(f)
        m["services"].append({"name": "unknown", "digest": "sha256:1", "tag": "1"})
        with open(manifest, "w") as f:
            json.dump(m, f)
            
        res = run_updater(values, manifest, summary)
        assert res.returncode != 0
        assert "UNKNOWN_PRODUCTION_COMPONENT" in res.stderr

if __name__ == "__main__":
    test_successful_update()
    test_unknown_service()
    print("PASS: Python updater tests successful")
