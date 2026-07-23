#!/usr/bin/env python3
"""Fail on HIGH/CRITICAL Trivy secrets without persisting matched values."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BLOCKING_SEVERITIES = {"HIGH", "CRITICAL"}
SAFE_FIELDS = (
    "RuleID",
    "Category",
    "Severity",
    "Title",
    "StartLine",
    "EndLine",
)


def load_report(path: Path) -> dict:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read Trivy JSON report {path}: {exc}") from exc
    if not isinstance(report, dict) or not isinstance(report.get("Results", []), list):
        raise ValueError("Trivy JSON report has no Results list")
    return report


def sanitized_findings(report: dict) -> list[dict]:
    findings = []
    for result in report.get("Results", []):
        target = result.get("Target", "unknown")
        if target.startswith("/src/"):
            target = target.removeprefix("/src/")
        for secret in result.get("Secrets") or []:
            severity = str(secret.get("Severity", "UNKNOWN")).upper()
            if severity not in BLOCKING_SEVERITIES:
                continue
            finding = {"Target": target}
            finding.update({field: secret.get(field) for field in SAFE_FIELDS})
            findings.append(finding)
    return sorted(
        findings,
        key=lambda item: (
            item.get("Severity") or "",
            item.get("Target") or "",
            item.get("StartLine") or 0,
            item.get("RuleID") or "",
        ),
    )


def evaluate(input_path: Path, report_path: Path, summary_path: Path) -> int:
    findings = sanitized_findings(load_report(input_path))
    severity_counts = {
        severity: sum(item.get("Severity") == severity for item in findings)
        for severity in ("HIGH", "CRITICAL")
    }
    sanitized = {
        "schemaVersion": 1,
        "scanner": "trivy-secret",
        "blockingSeverities": ["HIGH", "CRITICAL"],
        "findingCount": len(findings),
        "findings": findings,
    }
    summary = {
        "schemaVersion": 1,
        "verdict": "FAIL" if findings else "PASS",
        "findingCount": len(findings),
        "severityCounts": severity_counts,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(sanitized, indent=2) + "\n", encoding="utf-8")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    if findings:
        print(f"Secret gate failed with {len(findings)} HIGH/CRITICAL finding(s).")
        for item in findings:
            print(
                f"{item['Severity']} {item.get('RuleID')} "
                f"{item.get('Target')}:{item.get('StartLine')} {item.get('Title')}"
            )
        return 1
    print("Secret gate passed with 0 HIGH/CRITICAL findings.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    try:
        return evaluate(args.input, args.report, args.summary)
    except ValueError as exc:
        print(f"Secret report evaluation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
