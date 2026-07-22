#!/usr/bin/env python3
"""Validate PM-126 tfsec exceptions against exact Terraform resources."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path, PurePosixPath


REQUIRED_FIELDS = {
    "rule",
    "tfsecIgnore",
    "resource",
    "reason",
    "owner",
    "ticket",
    "reviewDate",
    "source",
    "status",
}
APPROVED_STATUSES = {
    "approved-false-positive",
    "approved-operational-necessity",
}
IGNORE_RE = re.compile(
    r"^\s*#tfsec:ignore:(?P<ignore>[a-z0-9-]+):exp:(?P<expiry>\d{4}-\d{2}-\d{2})\s*$",
    re.MULTILINE,
)


def load_ledger(path: Path) -> list[dict[str, object]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read exception ledger {path}: {exc}") from exc
    if payload.get("schemaVersion") != 1:
        raise ValueError("exception ledger schemaVersion must be 1")
    records = payload.get("exceptions")
    if not isinstance(records, list):
        raise ValueError("exception ledger 'exceptions' must be a list")
    return records


def terraform_block_pattern(resource: str) -> re.Pattern[str]:
    parts = resource.split(".")
    if parts[0] == "data" and len(parts) == 3:
        block_kind, resource_type, resource_name = "data", parts[1], parts[2]
    elif len(parts) == 2:
        block_kind, resource_type, resource_name = "resource", parts[0], parts[1]
    else:
        raise ValueError(f"unsupported Terraform resource address: {resource}")
    return re.compile(
        rf'^\s*{block_kind}\s+"{re.escape(resource_type)}"\s+"{re.escape(resource_name)}"\s*\{{\s*$',
        re.MULTILINE,
    )


def validate_record(
    record: object,
    *,
    repo_root: Path,
    today: dt.date,
) -> tuple[str, str, str]:
    if not isinstance(record, dict):
        raise ValueError("each exception must be a JSON object")
    missing = sorted(REQUIRED_FIELDS - record.keys())
    if missing:
        raise ValueError(f"exception is missing fields: {', '.join(missing)}")

    for field in REQUIRED_FIELDS:
        if not isinstance(record[field], str) or not record[field].strip():
            raise ValueError(f"exception field {field} must be a non-empty string")
    if record["status"] not in APPROVED_STATUSES:
        raise ValueError(
            f"{record['resource']}: status must be false-positive or operational necessity"
        )
    if record["ticket"] != "PM-126":
        raise ValueError(f"{record['resource']}: ticket must be PM-126")
    if not re.fullmatch(r"AVD-[A-Z]+-\d{4}", record["rule"]):
        raise ValueError(f"{record['resource']}: invalid AVD rule identifier")

    try:
        review_date = dt.date.fromisoformat(record["reviewDate"])
    except ValueError as exc:
        raise ValueError(f"{record['resource']}: reviewDate must be YYYY-MM-DD") from exc
    if review_date < today:
        raise ValueError(f"{record['resource']}: exception expired on {review_date}")

    source = PurePosixPath(record["source"])
    if source.is_absolute() or ".." in source.parts or source.suffix != ".tf":
        raise ValueError(f"{record['resource']}: source must be a repo-relative .tf file")
    source_path = repo_root / source
    try:
        text = source_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"{record['resource']}: cannot read {source}: {exc}") from exc

    metadata = {
        "rule": record["rule"],
        "resource": record["resource"],
        "owner": record["owner"],
        "ticket": record["ticket"],
        "review_date": record["reviewDate"],
    }
    for key, value in metadata.items():
        if f"# {key}={value}" not in text:
            raise ValueError(f"{record['resource']}: source is missing '# {key}={value}'")

    ignore_line = f"#tfsec:ignore:{record['tfsecIgnore']}:exp:{record['reviewDate']}"
    block_pattern = terraform_block_pattern(record["resource"])
    if not re.search(
        rf"{re.escape(ignore_line)}\s*\n{block_pattern.pattern}",
        text,
        flags=re.MULTILINE,
    ):
        raise ValueError(
            f"{record['resource']}: exact expiring ignore must be adjacent to its resource block"
        )
    return str(source), record["tfsecIgnore"], record["reviewDate"]


def validate(ledger: Path, repo_root: Path, today: dt.date) -> int:
    records = load_ledger(ledger)
    if not records:
        raise ValueError("exception ledger must not be empty while tfsec ignores exist")

    declared: set[tuple[str, str]] = set()
    expected_ignores: list[tuple[str, str, str]] = []
    for record in records:
        key = (record.get("rule", ""), record.get("resource", ""))
        if key in declared:
            raise ValueError(f"duplicate exception: {key[0]} on {key[1]}")
        declared.add(key)
        expected_ignores.append(validate_record(record, repo_root=repo_root, today=today))

    actual_ignores: list[tuple[str, str, str]] = []
    for terraform_file in sorted((repo_root / "infra").rglob("*.tf")):
        relative = terraform_file.relative_to(repo_root).as_posix()
        for match in IGNORE_RE.finditer(terraform_file.read_text(encoding="utf-8")):
            actual_ignores.append((relative, match["ignore"], match["expiry"]))

    if sorted(actual_ignores) != sorted(expected_ignores):
        undeclared = sorted(set(actual_ignores) - set(expected_ignores))
        missing = sorted(set(expected_ignores) - set(actual_ignores))
        raise ValueError(
            "tfsec ignores and ledger differ; "
            f"undeclared={undeclared or 'none'}, missing={missing or 'none'}"
        )
    print(f"Validated {len(records)} exact, unexpired PM-126 tfsec exceptions.")
    return len(records)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ledger",
        type=Path,
        default=Path("docs/evidence/mandate-10/pm-126-tfsec-exceptions.json"),
    )
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--today", type=dt.date.fromisoformat, default=dt.date.today())
    args = parser.parse_args()
    try:
        validate(args.ledger, args.repo_root.resolve(), args.today)
    except ValueError as exc:
        print(f"PM-126 exception validation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
