#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

import yaml


def load_yaml(path):
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def selector_matches_labels(selector, labels):
    match_labels = (selector or {}).get("matchLabels") or {}
    if not match_labels:
        return False
    labels = labels or {}
    for key, expected in match_labels.items():
        actual = labels.get(key)
        if actual == expected:
            continue
        if key == "app.kubernetes.io/name" and labels.get("app") == expected:
            continue
        if key == "app" and labels.get("app.kubernetes.io/name") == expected:
            continue
        return False
    return True


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
    exception_records = exceptions.get("exceptions", [])
    active_pods = {}
    for item in pods.get("items", []):
        metadata = item.get("metadata", {})
        uid = metadata.get("uid")
        if not uid:
            continue
        labels = metadata.get("labels") or {}
        active_pods[uid] = {
            "name": metadata.get("name"),
            "namespace": metadata.get("namespace"),
            "labels": labels,
            "app": labels.get("app.kubernetes.io/name") or labels.get("app"),
        }
    active_uids = set(active_pods)
    active_failures = []
    approved_exceptions = []
    stale_results = []
    unresolved_results = []

    for report in policyreports.get("items", []):
        scope = report.get("scope") or {}
        uid = scope.get("uid")
        source = "active" if uid in active_uids else "stale" if uid else "unresolved"
        for result in report.get("results") or []:
            if result.get("result") not in {"fail", "warn", "error"}:
                continue
            entry = {
                "policy": result.get("policy"),
                "rule": result.get("rule"),
                "resource": active_pods.get(uid, {}).get("name") or scope.get("name"),
                "namespace": active_pods.get(uid, {}).get("namespace") or scope.get("namespace"),
                "app": active_pods.get(uid, {}).get("app"),
                "category": source,
                "message": result.get("message"),
            }
            if source == "active":
                match = next(
                    (
                        exc
                        for exc in exception_records
                        if exc.get("policy") == entry["policy"]
                        and entry["rule"] in (exc.get("rules") or [])
                        and selector_matches_labels(
                            exc.get("selector"),
                            active_pods.get(uid, {}).get("labels"),
                        )
                    ),
                    None,
                )
                if match:
                    approved_exceptions.append({**entry, "exceptionId": match.get("id")})
                else:
                    active_failures.append(entry)
            elif source == "stale":
                stale_results.append(entry)
            else:
                unresolved_results.append(entry)

    sort_key = lambda item: (
        item.get("policy") or "",
        item.get("rule") or "",
        item.get("namespace") or "",
        item.get("resource") or "",
        item.get("exceptionId") or "",
    )
    active_failures.sort(key=sort_key)
    approved_exceptions.sort(key=sort_key)
    stale_results.sort(key=sort_key)
    unresolved_results.sort(key=sort_key)

    output = {
        "activeFailures": active_failures,
        "approvedExceptions": approved_exceptions,
        "staleResults": stale_results,
        "unresolvedResults": unresolved_results,
    }
    Path(args.output).write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    return 1 if active_failures or unresolved_results else 0


if __name__ == "__main__":
    raise SystemExit(main())
