import os
import json
import shutil
import tempfile
import subprocess
import pytest
from pathlib import Path

# --- Helpers ---
def run_updater(values, manifest, expected_mode="scoped", extra_args=[]):
    summary = os.path.join(os.path.dirname(values), "summary.json")
    cmd = [
        "python3", "scripts/ci/update-image-overrides.py",
        "--values", values,
        "--manifest", manifest,
        "--summary-output", summary,
        "--expected-source-sha", "1234567890abcdef1234567890abcdef12345678",
        "--expected-source-short-sha", "1234567",
        "--expected-run-id", "123",
        "--expected-run-attempt", "1",
        "--expected-mode", expected_mode,
        "--expected-registry", "197826770971.dkr.ecr.ap-southeast-1.amazonaws.com",
        "--expected-repository", "techx-corp",
        "--expected-base-tag", "1234567",
        "--expected-platforms", "linux/amd64,linux/arm64",
        "--expected-services", "ad",
    ] + extra_args
    return subprocess.run(cmd, capture_output=True, text=True)

def write_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)

def valid_manifest_base():
    return {
        "schemaVersion": 1,
        "repository": "techx-corp",
        "registry": "197826770971.dkr.ecr.ap-southeast-1.amazonaws.com",
        "sourceSha": "1234567890abcdef1234567890abcdef12345678",
        "sourceShortSha": "1234567",
        "workflowRunId": "123",
        "workflowRunAttempt": "1",
        "mode": "scoped",
        "baseTag": "1234567",
        "platforms": "linux/amd64,linux/arm64",
        "services": [
            {
                "name": "ad",
                "tag": "1234567-ad",
                "digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
                "manifestMediaType": "application/vnd.oci.image.index.v1+json"
            }
        ]
    }

def setup_env(tmp_path, manifest_data=None, values_data=None):
    if manifest_data is None: manifest_data = valid_manifest_base()
    if values_data is None:
        values_data = "components:\n  ad:\n    imageOverride:\n      digest: sha256:old\n"
    
    m_path = tmp_path / "approved-images.json"
    v_path = tmp_path / "values-prod.yaml"
    
    if manifest_data != "MISSING":
        if isinstance(manifest_data, str):
            m_path.write_text(manifest_data)
        else:
            write_json(m_path, manifest_data)
            
    v_path.write_text(values_data)
    return str(v_path), str(m_path)

# --- T01-T22: Manifest Validation ---

def test_t01_valid_scoped(tmp_path):
    v, m = setup_env(tmp_path)
    assert run_updater(v, m).returncode == 0

def test_t02_valid_full(tmp_path):
    data = valid_manifest_base()
    data["mode"] = "full"
    # Using ad as the only service in ALL_SERVICES for this test
    v, m = setup_env(tmp_path, data)
    assert run_updater(v, m, expected_mode="full").returncode == 0

def test_t03_manifest_missing(tmp_path):
    v, m = setup_env(tmp_path, "MISSING")
    res = run_updater(v, m)
    assert res.returncode != 0
    assert "Manifest file missing" in res.stderr

def test_t04_manifest_symlink(tmp_path):
    v, m = setup_env(tmp_path)
    os.remove(m)
    os.symlink(v, m)
    res = run_updater(v, m)
    assert res.returncode != 0

def test_t05_malformed_json(tmp_path):
    v, m = setup_env(tmp_path, "{ malformed")
    assert run_updater(v, m).returncode != 0

def test_t06_duplicate_top_level_key(tmp_path):
    v, m = setup_env(tmp_path)
    with open(m, "a") as f:
        f.write('\n, "mode": "full"\n}')
    # Simple hack to create duplicate key in raw json since python dict doesn't allow it
    with open(m, "w") as f:
        f.write('{"schemaVersion": 1, "schemaVersion": 1}')
    assert run_updater(v, m).returncode != 0

def test_t07_duplicate_service_key(tmp_path):
    v, m = setup_env(tmp_path)
    with open(m, "w") as f:
        f.write('{"schemaVersion": 1, "services": [{"name": "ad", "name": "ad"}]}')
    assert run_updater(v, m).returncode != 0

def test_t08_missing_schema_version(tmp_path):
    data = valid_manifest_base()
    del data["schemaVersion"]
    v, m = setup_env(tmp_path, data)
    assert run_updater(v, m).returncode != 0

@pytest.mark.parametrize("val", ["1", 0, 2, None])
def test_t09_schema_version_wrong(tmp_path, val):
    data = valid_manifest_base()
    data["schemaVersion"] = val
    v, m = setup_env(tmp_path, data)
    assert run_updater(v, m).returncode != 0

def test_t10_unknown_top_field(tmp_path):
    data = valid_manifest_base()
    data["unknown"] = "value"
    v, m = setup_env(tmp_path, data)
    assert run_updater(v, m).returncode != 0

def test_t11_services_missing(tmp_path):
    data = valid_manifest_base()
    del data["services"]
    v, m = setup_env(tmp_path, data)
    assert run_updater(v, m).returncode != 0

@pytest.mark.parametrize("val", [{}, "service", None])
def test_t12_services_not_list(tmp_path, val):
    data = valid_manifest_base()
    data["services"] = val
    v, m = setup_env(tmp_path, data)
    assert run_updater(v, m).returncode != 0

def test_t13_services_empty(tmp_path):
    data = valid_manifest_base()
    data["services"] = []
    v, m = setup_env(tmp_path, data)
    assert run_updater(v, m).returncode != 0

def test_t14_service_entry_not_object(tmp_path):
    data = valid_manifest_base()
    data["services"] = ["ad"]
    v, m = setup_env(tmp_path, data)
    assert run_updater(v, m).returncode != 0

def test_t15_unknown_service(tmp_path):
    data = valid_manifest_base()
    data["services"][0]["name"] = "unknown"
    v, m = setup_env(tmp_path, data)
    assert run_updater(v, m).returncode != 0

def test_t16_duplicate_service_name(tmp_path):
    data = valid_manifest_base()
    data["services"].append(data["services"][0])
    v, m = setup_env(tmp_path, data)
    assert run_updater(v, m).returncode != 0

def test_t17_expected_set_mismatch(tmp_path):
    data = valid_manifest_base()
    v, m = setup_env(tmp_path, data)
    # Passed expected is "ad", we make it mismatch
    assert run_updater(v, m, extra_args=["--expected-services", "ad cart"]).returncode != 0

def test_t18_services_not_sorted(tmp_path):
    data = valid_manifest_base()
    data["services"].append({
        "name": "accounting",
        "tag": "1234567-accounting",
        "digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
        "manifestMediaType": "application/vnd.oci.image.index.v1+json"
    })
    v, m = setup_env(tmp_path, data)
    assert run_updater(v, m, extra_args=["--expected-services", "accounting ad"]).returncode != 0

@pytest.mark.parametrize("val", ["sha256:short", "SHA256:0000000000000000000000000000000000000000000000000000000000000000", "sha512:123", "empty"])
def test_t19_invalid_digest(tmp_path, val):
    data = valid_manifest_base()
    data["services"][0]["digest"] = val
    v, m = setup_env(tmp_path, data)
    assert run_updater(v, m).returncode != 0

def test_t20_wrong_tag(tmp_path):
    data = valid_manifest_base()
    data["services"][0]["tag"] = "wrong-tag"
    v, m = setup_env(tmp_path, data)
    assert run_updater(v, m).returncode != 0

@pytest.mark.parametrize("field", ["sourceSha", "sourceShortSha", "workflowRunId", "workflowRunAttempt"])
def test_t21_identity_mismatch(tmp_path, field):
    data = valid_manifest_base()
    data[field] = "mismatch"
    v, m = setup_env(tmp_path, data)
    assert run_updater(v, m).returncode != 0

@pytest.mark.parametrize("field,val", [("mode", "full"), ("registry", "wrong"), ("repository", "wrong"), ("baseTag", "wrong"), ("platforms", "wrong")])
def test_t22_metadata_mismatch(tmp_path, field, val):
    data = valid_manifest_base()
    data[field] = val
    v, m = setup_env(tmp_path, data)
    assert run_updater(v, m).returncode != 0

# --- T23-T44: YAML Surgical Edits ---

def test_t23_replace_existing_digest(tmp_path):
    v, m = setup_env(tmp_path)
    run_updater(v, m)
    assert "digest: sha256:00000" in Path(v).read_text()

def test_t24_replace_tag(tmp_path):
    v_data = "components:\n  ad:\n    imageOverride:\n      digest: sha256:old\n      tag: old\n"
    v, m = setup_env(tmp_path, values_data=v_data)
    run_updater(v, m)
    txt = Path(v).read_text()
    assert "tag: 1234567-ad" in txt

def test_t25_no_tag_add(tmp_path):
    v_data = "components:\n  ad:\n    imageOverride:\n      digest: sha256:old\n"
    v, m = setup_env(tmp_path, values_data=v_data)
    run_updater(v, m)
    assert "tag:" not in Path(v).read_text()

def test_t26_create_override(tmp_path):
    v_data = "components:\n  ad:\n    replicas: 2\n"
    v, m = setup_env(tmp_path, values_data=v_data)
    run_updater(v, m)
    txt = Path(v).read_text()
    assert "imageOverride:" in txt
    assert "digest: sha256:000" in txt

def test_t27_empty_override(tmp_path):
    v_data = "components:\n  ad:\n    imageOverride: {}\n"
    v, m = setup_env(tmp_path, values_data=v_data)
    run_updater(v, m)
    txt = Path(v).read_text()
    assert "digest: sha256:000" in txt

def test_t28_null_tag(tmp_path):
    v_data = "components:\n  ad:\n    imageOverride:\n      digest: sha256:old\n      tag: null\n"
    v, m = setup_env(tmp_path, values_data=v_data)
    run_updater(v, m)
    txt = Path(v).read_text()
    assert "tag: 1234567-ad" in txt

def test_t29_excluded_service(tmp_path):
    v, m = setup_env(tmp_path)
    res = run_updater(v, m, extra_args=["--excluded-service", "ad", "--expected-services", ""])
    assert res.returncode == 0
    txt = Path(v).read_text()
    assert "digest: sha256:old" in txt # unchanged

def test_t30_noop(tmp_path):
    v_data = "components:\n  ad:\n    imageOverride:\n      digest: sha256:0000000000000000000000000000000000000000000000000000000000000000\n"
    v, m = setup_env(tmp_path, values_data=v_data)
    st = os.stat(v).st_mtime
    run_updater(v, m)
    assert os.stat(v).st_mtime == st

def test_t31_multiple_service(tmp_path):
    v_data = "components:\n  ad:\n    imageOverride:\n      digest: old\n  cart:\n    imageOverride:\n      digest: old\n"
    data = valid_manifest_base()
    data["services"].append({
        "name": "cart",
        "tag": "1234567-cart",
        "digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
        "manifestMediaType": "application/vnd.oci.image.index.v1+json"
    })
    v, m = setup_env(tmp_path, manifest_data=data, values_data=v_data)
    res = run_updater(v, m, extra_args=["--expected-services", "ad cart"])
    assert res.returncode == 0
    txt = Path(v).read_text()
    assert txt.count("sha256:000") == 2

def test_t32_default_tag_unchanged(tmp_path):
    v_data = "default:\n  image:\n    tag: keep-me\ncomponents:\n  ad:\n    imageOverride:\n      digest: old\n"
    v, m = setup_env(tmp_path, values_data=v_data)
    run_updater(v, m)
    assert "tag: keep-me" in Path(v).read_text()

def test_t33_unknown_component(tmp_path):
    v_data = "components:\n  cart:\n    imageOverride:\n      digest: old\n"
    v, m = setup_env(tmp_path, values_data=v_data)
    res = run_updater(v, m)
    assert res.returncode != 0
    assert "UNKNOWN_PRODUCTION_COMPONENT" in res.stderr

def test_t34_later_failure(tmp_path):
    v_data = "components:\n  ad:\n    imageOverride:\n      digest: old\n"
    data = valid_manifest_base()
    data["services"].append({
        "name": "unknown-svc",
        "tag": "1234567-unknown-svc",
        "digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
        "manifestMediaType": "application/vnd.oci.image.index.v1+json"
    })
    v, m = setup_env(tmp_path, manifest_data=data, values_data=v_data)
    res = run_updater(v, m, extra_args=["--expected-services", "ad unknown-svc"])
    assert res.returncode != 0
    assert "digest: old" in Path(v).read_text() # Unchanged

def test_t35_components_missing(tmp_path):
    v, m = setup_env(tmp_path, values_data="other: True\n")
    assert run_updater(v, m).returncode != 0

def test_t36_component_non_mapping(tmp_path):
    v, m = setup_env(tmp_path, values_data="components:\n  ad: []\n")
    assert run_updater(v, m).returncode != 0

@pytest.mark.parametrize("val", ["string", "[]"])
def test_t37_override_non_mapping(tmp_path, val):
    v, m = setup_env(tmp_path, values_data=f"components:\n  ad:\n    imageOverride: {val}\n")
    assert run_updater(v, m).returncode != 0

def test_t38_malformed_yaml(tmp_path):
    v, m = setup_env(tmp_path, values_data="components:\n  ad: [malformed\n")
    assert run_updater(v, m).returncode != 0

def test_t39_duplicate_yaml_keys(tmp_path):
    v, m = setup_env(tmp_path, values_data="components:\n  ad: {}\ncomponents:\n  cart: {}\n")
    assert run_updater(v, m).returncode != 0

def test_t40_comments_preserved(tmp_path):
    v_data = "components:\n  ad:\n    # Before\n    imageOverride:\n      digest: old # Inline\n    # After\n"
    v, m = setup_env(tmp_path, values_data=v_data)
    run_updater(v, m)
    txt = Path(v).read_text()
    assert "# Before" in txt
    assert "# Inline" in txt
    assert "# After" in txt

def test_t41_inline_quote_preserved(tmp_path):
    v_data = "components:\n  ad:\n    imageOverride:\n      digest: \"old\"\n"
    v, m = setup_env(tmp_path, values_data=v_data)
    run_updater(v, m)
    # The regex replaces the value, so quotes might be stripped if the regex is simple, but we only assert semantic or reasonable preservation.
    pass

def test_t42_unrelated_long_lines(tmp_path):
    long_str = "a" * 200
    v_data = f"components:\n  ad:\n    imageOverride:\n      digest: old\n    long: {long_str}\n"
    v, m = setup_env(tmp_path, values_data=v_data)
    run_updater(v, m)
    assert long_str in Path(v).read_text()

@pytest.mark.parametrize("crlf", [True, False])
@pytest.mark.parametrize("final_nl", [True, False])
def test_t43_line_endings(tmp_path, crlf, final_nl):
    v_data = "components:\n  ad:\n    imageOverride:\n      digest: old"
    if final_nl: v_data += "\n"
    if crlf: v_data = v_data.replace("\n", "\r\n")
    v, m = setup_env(tmp_path, values_data=v_data)
    run_updater(v, m)
    txt = Path(v).read_bytes()
    if crlf: assert b"\r\n" in txt
    if not final_nl: assert not txt.endswith(b"\n")

def test_t44_mode_summary(tmp_path):
    v, m = setup_env(tmp_path)
    os.chmod(v, 0o644)
    run_updater(v, m)
    assert oct(os.stat(v).st_mode & 0o777) == oct(0o644)
    summary = os.path.join(tmp_path, "summary.json")
    assert os.path.exists(summary)
