import os
import json
import subprocess
import pytest
from pathlib import Path

def run_verifier(rendered, manifest, extra_args=[]):
    cmd = [
        "python3", "scripts/ci/verify-rendered-images.py",
        "--rendered", rendered,
        "--manifest", manifest,
        "--registry", "197826770971.dkr.ecr.ap-southeast-1.amazonaws.com",
        "--repository", "techx-corp",
    ] + extra_args
    return subprocess.run(cmd, capture_output=True, text=True)

def setup_env(tmp_path, manifest_data, rendered_data):
    m_path = tmp_path / "approved-images.json"
    r_path = tmp_path / "rendered.yaml"
    m_path.write_text(json.dumps(manifest_data))
    r_path.write_text(rendered_data)
    return str(r_path), str(m_path)

def valid_manifest():
    return {
        "services": [
            {
                "name": "ad",
                "tag": "123-ad",
                "digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000"
            }
        ]
    }

def test_t45_valid_service_mapping(tmp_path):
    rendered = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ad
  labels:
    app.kubernetes.io/name: ad
spec:
  template:
    spec:
      containers:
      - image: 197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp@sha256:0000000000000000000000000000000000000000000000000000000000000000
"""
    r, m = setup_env(tmp_path, valid_manifest(), rendered)
    assert run_verifier(r, m).returncode == 0

def test_t45a_wrong_registry(tmp_path):
    rendered = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ad
  labels:
    app.kubernetes.io/name: ad
spec:
  template:
    spec:
      containers:
      - image: malicious.example.com/techx-corp@sha256:0000000000000000000000000000000000000000000000000000000000000000
"""
    r, m = setup_env(tmp_path, valid_manifest(), rendered)
    assert run_verifier(r, m).returncode != 0

def test_t45b_wrong_repository(tmp_path):
    rendered = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ad
  labels:
    app.kubernetes.io/name: ad
spec:
  template:
    spec:
      containers:
      - image: 197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp-shadow@sha256:0000000000000000000000000000000000000000000000000000000000000000
"""
    r, m = setup_env(tmp_path, valid_manifest(), rendered)
    assert run_verifier(r, m).returncode != 0

def test_t45c_exact_match(tmp_path):
    rendered = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ad
  labels:
    app.kubernetes.io/name: ad
spec:
  template:
    spec:
      containers:
      - image: 197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp@sha256:0000000000000000000000000000000000000000000000000000000000000000
"""
    r, m = setup_env(tmp_path, valid_manifest(), rendered)
    assert run_verifier(r, m).returncode == 0

def test_t45d_sidecar_wrong_app_wrong(tmp_path):
    rendered = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ad
  labels:
    app.kubernetes.io/name: ad
spec:
  template:
    spec:
      containers:
      - name: sidecar
        image: 197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp@sha256:0000000000000000000000000000000000000000000000000000000000000000
      - name: ad
        image: 197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp@sha256:1111111111111111111111111111111111111111111111111111111111111111
"""
    r, m = setup_env(tmp_path, valid_manifest(), rendered)
    # The script looks at all containers that match repository `techx-corp`.
    # Since both match `techx-corp`, both are checked. The second one fails.
    assert run_verifier(r, m).returncode != 0

def test_t46_expected_workload_missing(tmp_path):
    r, m = setup_env(tmp_path, valid_manifest(), "kind: Deployment\n")
    assert run_verifier(r, m).returncode != 0

def test_t47_wrong_digest(tmp_path):
    rendered = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ad
  labels:
    app.kubernetes.io/name: ad
spec:
  template:
    spec:
      containers:
      - image: 197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp@sha256:1111111111111111111111111111111111111111111111111111111111111111
"""
    r, m = setup_env(tmp_path, valid_manifest(), rendered)
    assert run_verifier(r, m).returncode != 0

def test_t48_swapped_digest(tmp_path):
    man = valid_manifest()
    man["services"].append({"name": "cart", "tag": "123-cart", "digest": "sha256:111"})
    rendered = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ad
spec:
  template:
    metadata:
      labels:
        app.kubernetes.io/name: ad
    spec:
      containers:
      - image: 197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp@sha256:111
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cart
spec:
  template:
    metadata:
      labels:
        app.kubernetes.io/name: cart
    spec:
      containers:
      - image: 197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp@sha256:0000000000000000000000000000000000000000000000000000000000000000
"""
    r, m = setup_env(tmp_path, man, rendered)
    assert run_verifier(r, m).returncode != 0

def test_t49_mutable_tag(tmp_path):
    rendered = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ad
  labels:
    app.kubernetes.io/name: ad
spec:
  template:
    spec:
      containers:
      - image: 197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp:123-ad
"""
    r, m = setup_env(tmp_path, valid_manifest(), rendered)
    assert run_verifier(r, m).returncode != 0

def test_t50_excluded_service(tmp_path):
    man = valid_manifest()
    man["services"].append({"name": "flagd-ui", "tag": "123-flagd-ui", "digest": "sha256:222"})
    rendered = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ad
  labels:
    app.kubernetes.io/name: ad
spec:
  template:
    spec:
      containers:
      - image: 197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp@sha256:0000000000000000000000000000000000000000000000000000000000000000
"""
    # Excluded service flagd-ui missing from rendered is OK.
    r, m = setup_env(tmp_path, man, rendered)
    assert run_verifier(r, m, ["--excluded-service", "flagd-ui"]).returncode == 0
