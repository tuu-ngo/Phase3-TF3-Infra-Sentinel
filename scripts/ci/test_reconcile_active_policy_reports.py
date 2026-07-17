import json
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ci" / "reconcile-active-policy-reports.py"


def test_reconcile_matches_app_label_fallback(tmp_path):
    policyreports = tmp_path / "policyreports.yaml"
    pods = tmp_path / "pods.json"
    exceptions = tmp_path / "exceptions.yaml"
    output = tmp_path / "output.json"

    policyreports.write_text(
        """
items:
  - scope:
      uid: pod-uid-1
      name: aiops-engine-76698db4cd-xzthk
      namespace: techx-tf3
    results:
      - policy: custom-baseline-security-context
        rule: require-allow-privilege-escalation-false
        result: fail
        message: allowPrivilegeEscalation must be set to false.
""".strip()
        + "\n",
        encoding="utf-8",
    )
    pods.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "metadata": {
                            "uid": "pod-uid-1",
                            "name": "aiops-engine-76698db4cd-xzthk",
                            "namespace": "techx-tf3",
                            "labels": {"app": "aiops-engine"},
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    exceptions.write_text(
        """
schemaVersion: 1
exceptions:
  - id: m05-aiops-engine-runtime-hardening
    policy: custom-baseline-security-context
    rules:
      - require-allow-privilege-escalation-false
    selector:
      matchLabels:
        app.kubernetes.io/name: aiops-engine
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--policyreports",
            str(policyreports),
            "--pods",
            str(pods),
            "--exceptions",
            str(exceptions),
            "--output",
            str(output),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["activeFailures"] == []
    assert len(data["approvedExceptions"]) == 1
    assert data["approvedExceptions"][0]["app"] == "aiops-engine"


def test_reconcile_matches_app_kubernetes_name_alias(tmp_path):
    policyreports = tmp_path / "policyreports.yaml"
    pods = tmp_path / "pods.json"
    exceptions = tmp_path / "exceptions.yaml"
    output = tmp_path / "output.json"

    policyreports.write_text(
        """
items:
  - scope:
      uid: pod-uid-2
      name: aiops-engine-5586b98c6-szc9g
      namespace: techx-tf3
    results:
      - policy: custom-baseline-security-context
        rule: drop-all-capabilities
        result: fail
        message: Containers must drop all capabilities.
""".strip()
        + "\n",
        encoding="utf-8",
    )
    pods.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "metadata": {
                            "uid": "pod-uid-2",
                            "name": "aiops-engine-5586b98c6-szc9g",
                            "namespace": "techx-tf3",
                            "labels": {"app.kubernetes.io/name": "aiops-engine"},
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    exceptions.write_text(
        """
schemaVersion: 1
exceptions:
  - id: m05-aiops-engine-runtime-hardening
    policy: custom-baseline-security-context
    rules:
      - drop-all-capabilities
    selector:
      matchLabels:
        app: aiops-engine
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--policyreports",
            str(policyreports),
            "--pods",
            str(pods),
            "--exceptions",
            str(exceptions),
            "--output",
            str(output),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["activeFailures"] == []
    assert len(data["approvedExceptions"]) == 1
    assert data["approvedExceptions"][0]["app"] == "aiops-engine"
