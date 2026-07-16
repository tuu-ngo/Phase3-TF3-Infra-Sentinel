#!/usr/bin/env python3
import argparse
import json
from collections import defaultdict
from pathlib import Path

import yaml


def load_yaml(path):
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--policyreports", required=True)
    parser.add_argument("--pods", required=True)
    parser.add_argument("--exceptions")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    policyreports = load_yaml(args.policyreports)
    pods = load_json(args.pods)
    exceptions = load_yaml(args.exceptions) if args.exceptions else {"exceptions": []}
    approved = {
        (
            exc.get("policy"),
            tuple(exc.get("rules") or []),
            exc.get("selector", {}).get("matchLabels", {}).get("app.kubernetes.io/name"),
        )
        for exc in exceptions.get("exceptions", [])
    }

    active_uids = {item["metadata"]["uid"] for item in pods.get("items", []) if item.get("metadata", {}).get("uid")}
    active_failures = []
    stale_results = []
    unresolved_results = []

    for report in policyreports.get("items", []):
        scope = report.get("scope") or {}
        uid = scope.get("uid")
        source = "active" if uid in active_uids else "stale" if uid else "unresolved"
        for result in report.get("results") or []:
            entry = {
                "policy": result.get("policy"),
                "rule": result.get("rule"),
                "resource": result.get("resource", {}).get("name"),
                "namespace": result.get("resource", {}).get("namespace"),
                "category": source,
                "message": result.get("message"),
            }
            if source == "active":
                active_failures.append(entry)
            elif source == "stale":
                stale_results.append(entry)
            else:
                unresolved_results.append(entry)

    output = {
        "activeFailures": active_failures,
        "approvedExceptions": [
            {"policy": policy, "rules": list(rules), "app": app}
            for policy, rules, app in sorted(approved)
        ],
        "staleResults": stale_results,
        "unresolvedResults": unresolved_results,
    }
    Path(args.output).write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    return 1 if active_failures or unresolved_results else 0


if __name__ == "__main__":
    raise SystemExit(main())
