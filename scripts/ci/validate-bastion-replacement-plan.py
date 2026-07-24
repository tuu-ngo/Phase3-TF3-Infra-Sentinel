#!/usr/bin/env python3
"""Fail closed when a production Terraform plan replaces the shared bastion."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


BASTION_ADDRESS = "module.access.aws_instance.bastion"


def is_replacement(actions: object) -> bool:
    if not isinstance(actions, list):
        return False
    return "create" in actions and "delete" in actions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path, help="terraform show -json output")
    parser.add_argument(
        "--allow-replacement",
        choices=("true", "false"),
        default="false",
        help="explicit workflow-dispatch acknowledgement for a reviewed migration",
    )
    parser.add_argument(
        "--ticket",
        default="",
        help="approved maintenance ticket/reference required when replacement is allowed",
    )
    args = parser.parse_args()

    try:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read Terraform JSON plan: {exc}")
        return 2

    replacements = [
        change
        for change in plan.get("resource_changes", [])
        if change.get("address") == BASTION_ADDRESS
        and is_replacement(change.get("change", {}).get("actions"))
    ]

    if not replacements:
        print("PASS: shared bastion is not being replaced by this Terraform plan.")
        return 0

    if args.allow_replacement != "true":
        print(
            "ERROR: plan replaces the shared bastion. Stop before Apply; "
            "use a reviewed maintenance window and set "
            "allow_bastion_replacement=true with a ticket/reference."
        )
        return 1

    if not args.ticket.strip():
        print(
            "ERROR: allow_bastion_replacement=true requires a non-empty "
            "bastion_replacement_ticket/reference."
        )
        return 1

    print(
        "PASS: shared bastion replacement explicitly acknowledged for "
        f"maintenance reference {args.ticket.strip()!r}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
