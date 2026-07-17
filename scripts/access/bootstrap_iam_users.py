#!/usr/bin/env python3
"""Create the approved TF3 IAM source users and a protected credential handoff."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import string
from typing import Callable


OPERATOR_USERS = ("cdo01-pm", "cdo01-tl", "cdo02-pm", "cdo02-tl")
READONLY_USER = "tf3-members-readonly"
EXPECTED_ACCOUNT = "197826770971"


def generate_password() -> str:
    alphabet = string.ascii_letters + string.digits + "!@#%^*-_=+"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(32))
        if (
            any(char.islower() for char in password)
            and any(char.isupper() for char in password)
            and any(char.isdigit() for char in password)
            and any(char in "!@#%^*-_=+" for char in password)
        ):
            return password


def _reserve_handoff(path: Path) -> None:
    path.parent.resolve(strict=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)


def _write_handoff(path: Path, records: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8") as handoff:
        json.dump(records, handoff, indent=2)
        handoff.write("\n")
        handoff.flush()
        os.fsync(handoff.fileno())
    path.chmod(0o600)


def _exists(getter: Callable[..., object], username: str, missing_error: type[Exception]) -> bool:
    try:
        getter(UserName=username)
    except missing_error:
        return False
    return True


def bootstrap_users(
    iam_client,
    account_alias: str,
    output_path: Path,
    password_factory: Callable[[], str] = generate_password,
) -> list[dict[str, str]]:
    """Create missing users/credentials without modifying existing credentials."""
    if account_alias != EXPECTED_ACCOUNT:
        raise ValueError(f"Refusing mutation: expected AWS account {EXPECTED_ACCOUNT}")

    output_path = output_path.resolve()
    _reserve_handoff(output_path)
    records: list[dict[str, str]] = []
    _write_handoff(output_path, records)

    for username in (*OPERATOR_USERS, READONLY_USER):
        if not _exists(iam_client.get_user, username, iam_client.exceptions.NoSuchEntityException):
            iam_client.create_user(
                UserName=username,
                Tags=[{"Key": "ManagedBy", "Value": "tf3-production-access-bootstrap"}],
            )

        record = {"UserName": username}
        if _exists(iam_client.get_login_profile, username, iam_client.exceptions.NoSuchEntityException):
            record["LoginProfileStatus"] = "existing-login-profile"
        else:
            password = password_factory()
            iam_client.create_login_profile(
                UserName=username,
                Password=password,
                PasswordResetRequired=username in OPERATOR_USERS,
            )
            record["Password"] = password
            record["LoginProfileStatus"] = "created"

        records.append(record)
        _write_handoff(output_path, records)

        existing_keys = iam_client.list_access_keys(UserName=username)["AccessKeyMetadata"]
        if existing_keys:
            record["AccessKeyStatus"] = "existing-access-key-not-retrievable"
        else:
            key = iam_client.create_access_key(UserName=username)["AccessKey"]
            record["AccessKeyId"] = key["AccessKeyId"]
            record["SecretAccessKey"] = key["SecretAccessKey"]
            record["AccessKeyStatus"] = "created"

        _write_handoff(output_path, records)

    return records


def _outside_git_root(path: Path) -> bool:
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            try:
                path.resolve().relative_to(candidate)
            except ValueError:
                return True
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not _outside_git_root(args.output):
        parser.error("--output must be outside the Git repository")

    import boto3

    session = boto3.session.Session()
    account_id = session.client("sts").get_caller_identity()["Account"]
    records = bootstrap_users(session.client("iam"), account_id, args.output)
    for record in records:
        print(
            f"{record['UserName']}: "
            f"login={record['LoginProfileStatus']} access-key={record['AccessKeyStatus']}"
        )
    print(f"Credential handoff created at {args.output.resolve()} (mode 0600)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
