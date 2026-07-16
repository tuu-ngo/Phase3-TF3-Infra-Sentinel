import os
import yaml
import pytest
from pathlib import Path

from ruamel.yaml import YAML

def get_workflows():
    yaml = YAML(typ="safe")
    build = yaml.load(Path(".github/workflows/build-push-ecr.yml").read_text())
    pr = yaml.load(Path(".github/workflows/test-image-bump.yml").read_text())
    return build, pr

def test_t51_actionlint_passes():
    import subprocess
    actionlint_path = Path("actionlint")
    if actionlint_path.exists():
        res = subprocess.run(["./actionlint", ".github/workflows/build-push-ecr.yml", ".github/workflows/test-image-bump.yml"], capture_output=True)
        assert res.returncode == 0

def test_t52_production_two_jobs():
    build, _ = get_workflows()
    jobs = build.get("jobs", {})
    assert set(jobs.keys()) == {"build-scan", "open-image-bump-pr"}
    assert jobs["open-image-bump-pr"].get("needs") == "build-scan"

def test_t53_permissions_separated():
    build, _ = get_workflows()
    jobs = build.get("jobs", {})
    
    bs_perms = jobs["build-scan"].get("permissions", {})
    assert bs_perms.get("id-token") == "write"
    assert bs_perms.get("contents") == "read"
    assert "pull-requests" not in bs_perms
    
    pr_perms = jobs["open-image-bump-pr"].get("permissions", {})
    assert pr_perms.get("contents") == "write"
    assert pr_perms.get("pull-requests") == "write"
    assert "id-token" not in pr_perms

def test_t54_artifact_branch_identity():
    build_raw = Path(".github/workflows/build-push-ecr.yml").read_text()
    assert "approved-images-${{ github.run_id }}-${{ github.run_attempt }}" in build_raw
    assert "ci/bump-images-${{ github.run_id }}-${{ github.run_attempt }}" in build_raw

def test_t55_publication_fail_closed():
    build_raw = Path(".github/workflows/build-push-ecr.yml").read_text()
    assert "git push origin" not in build_raw or "|| true" not in build_raw
    assert "git push --force" not in build_raw
    assert "git commit --amend" not in build_raw
    assert "git push --set-upstream origin \"$BRANCH_NAME\"" in build_raw
    assert "REMOTE_SHA" in build_raw
    assert "gh pr create" in build_raw
    assert "headRefOid" in build_raw

def test_t56_tests_installed_and_run():
    build_raw = Path(".github/workflows/build-push-ecr.yml").read_text()
    assert "python -m pip install" in build_raw
    assert "scripts/ci/requirements-image-bump.txt" in build_raw
    assert "python -m pytest" in build_raw

def test_t57_strict_metadata_passed():
    build_raw = Path(".github/workflows/build-push-ecr.yml").read_text()
    assert "--expected-source-sha" in build_raw
    assert "--expected-mode" in build_raw
    assert "--expected-registry" in build_raw
    assert "--expected-repository" in build_raw

def test_t58_trivy_contract():
    build_raw = Path(".github/workflows/build-push-ecr.yml").read_text()
    assert "v0.72.0" in build_raw
    assert "@${digest}" in build_raw
    build, _ = get_workflows()
    steps = build["jobs"]["build-scan"]["steps"]
    trivy_idx = next((i for i, s in enumerate(steps) if "trivy image" in s.get("run", "")), -1)
    upload_idx = next((i for i, s in enumerate(steps) if "actions/upload-artifact" in s.get("uses", "")), -1)
    assert trivy_idx != -1
    assert upload_idx != -1
    assert trivy_idx < upload_idx

def test_t59_validation_workflow_security():
    _, pr = get_workflows()
    on_block = pr.get("on") or pr.get(True)
    assert on_block.get("pull_request") is not None
    assert pr.get("permissions", {}).get("contents") == "read"
    assert pr.get("permissions", {}).get("id-token") is None

def test_t60_shell_git_safety():
    build_raw = Path(".github/workflows/build-push-ecr.yml").read_text()
    assert "set -euo pipefail" in build_raw
    assert "git push -f" not in build_raw
    assert "git rebase" not in build_raw
