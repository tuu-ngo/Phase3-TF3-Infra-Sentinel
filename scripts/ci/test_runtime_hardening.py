import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
CHART = REPO / "phase3 - information" / "techx-corp-chart"
VALUES = [
    CHART / "values.yaml",
    REPO / "phase3 - information" / "deploy" / "values-flagd-sync.yaml",
    REPO / "phase3 - information" / "deploy" / "values-prod.yaml",
    REPO / "phase3 - information" / "deploy" / "values-aio-llm.yaml",
]
EXCEPTIONS = REPO / "docs" / "evidence" / "mandate-05" / "exception-register.yaml"
VERIFY = REPO / "scripts" / "ci" / "verify-runtime-hardening.py"


def render_chart_with_dependencies(chart_dir, values):
    with tempfile.TemporaryDirectory() as tmpdir:
        chart_copy = Path(tmpdir) / chart_dir.name
        shutil.copytree(chart_dir, chart_copy)
        subprocess.run(
            ["helm", "dependency", "build", str(chart_copy)],
            cwd=REPO,
            check=True,
            capture_output=True,
            text=True,
        )

        render_result = subprocess.run(
            [
                "helm",
                "template",
                "techx-corp",
                str(chart_copy),
                "--namespace",
                "techx-tf3",
                *sum((["-f", str(path)] for path in values), []),
            ],
            cwd=REPO,
            check=True,
            capture_output=True,
            text=True,
        )
        return render_result.stdout


def test_authoritative_render_is_inventory_clean():
    if shutil.which("helm") is None:
        pytest.skip("helm is required for runtime hardening tests")

    with tempfile.TemporaryDirectory() as tmpdir:
        rendered = Path(tmpdir) / "rendered.yaml"
        inventory = Path(tmpdir) / "inventory.json"

        rendered.write_text(render_chart_with_dependencies(CHART, VALUES), encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                str(VERIFY),
                "--rendered",
                str(rendered),
                "--first-party-repository",
                "197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp",
                "--exception-register",
                str(EXCEPTIONS),
                "--mode",
                "inventory",
                "--output",
                str(inventory),
            ],
            cwd=REPO,
            check=True,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        data = json.loads(inventory.read_text(encoding="utf-8"))
        assert data["inventoryDelta"] == {"missing": [], "unexpected": []}
        assert data["summary"]["unresolvedFindingCount"] == 0
