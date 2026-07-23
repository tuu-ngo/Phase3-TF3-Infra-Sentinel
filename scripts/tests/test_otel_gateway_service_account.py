#!/usr/bin/env python3
"""Verify the OTEL gateway keeps its identity without the legacy collector."""

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "phase3 - information/techx-corp-chart"
PRODUCTION_VALUES = ROOT / "phase3 - information/deploy/values-prod.yaml"


def main() -> None:
    rendered = subprocess.run(
        [
            "helm",
            "template",
            "techx-corp",
            str(CHART),
            "--namespace",
            "techx-tf3",
            "--values",
            str(PRODUCTION_VALUES),
            "--set",
            "opentelemetry-collector.enabled=false",
            "--show-only",
            "templates/otel-gateway.yaml",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert "kind: ServiceAccount\nmetadata:\n  name: otel-gateway\n" in rendered, (
        "otel-gateway must render a dedicated ServiceAccount when the legacy "
        "collector is disabled"
    )
    assert "serviceAccountName: otel-gateway" in rendered, (
        "otel-gateway Deployment must use its dedicated ServiceAccount"
    )
    assert "serviceAccountName: otel-collector" not in rendered, (
        "otel-gateway must not depend on the legacy collector ServiceAccount"
    )
    assert "kind: ClusterRole\nmetadata:\n  name: otel-gateway\n" in rendered, (
        "otel-gateway must retain read-only Kubernetes metadata access"
    )
    assert "kind: ClusterRoleBinding\nmetadata:\n  name: otel-gateway\n" in rendered, (
        "otel-gateway ServiceAccount must be bound to its dedicated ClusterRole"
    )
    assert "resources: [\"pods\", \"namespaces\"]" in rendered
    assert "resources: [\"replicasets\"]" in rendered
    assert "verbs: [\"get\", \"list\", \"watch\"]" in rendered

    print("PASS: otel-gateway renders its dedicated identity and read-only RBAC")


if __name__ == "__main__":
    main()
