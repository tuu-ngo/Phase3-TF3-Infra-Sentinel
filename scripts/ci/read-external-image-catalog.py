#!/usr/bin/env python3
"""Emit the reviewed external image catalog as a scan-ready line list."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


def load_allowlist_reader():
    path = Path(__file__).with_name("verify-external-image-allowlist.py")
    spec = importlib.util.spec_from_file_location("verify_external_image_allowlist", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.read_allowlist


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allowlist", required=True, type=Path)
    parser.add_argument(
        "--first-party-repository",
        default="197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        read_allowlist = load_allowlist_reader()
        for image in read_allowlist(args.allowlist, args.first_party_repository):
            print(image)
    except Exception as exc:  # noqa: BLE001 - CLI must fail without a traceback.
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
