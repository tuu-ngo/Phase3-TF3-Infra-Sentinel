#!/usr/bin/env python3
"""Require the reviewed external image catalog to exactly match Helm render."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml


DIGEST_RE = re.compile(r"@sha256:[0-9a-f]{64}$")
INVENTORY_SCRIPT = Path(__file__).with_name("render-image-inventory.py")


def load_inventory_builder():
    spec = importlib.util.spec_from_file_location("render_image_inventory", INVENTORY_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to import {INVENTORY_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_inventory


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rendered", required=True, type=Path)
    parser.add_argument("--allowlist", required=True, type=Path)
    parser.add_argument("--first-party-repository", required=True)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def read_allowlist(path: Path, repository: str) -> list[str]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("schemaVersion") != 1:
        raise ValueError("allow-list schemaVersion must be 1")
    if document.get("firstPartyRepository") != repository:
        raise ValueError("allow-list firstPartyRepository does not match the requested repository")
    entries = document.get("images")
    if not isinstance(entries, list):
        raise ValueError("allow-list images must be a list")

    images: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("image"), str):
            raise ValueError("each allow-list entry must contain an image")
        image = entry["image"]
        if image.startswith(f"{repository}:") or image.startswith(f"{repository}@"):
            raise ValueError(f"first-party image must not be in external allow-list: {image}")
        if not DIGEST_RE.search(image):
            raise ValueError(f"external image must end with an exact digest: {image}")
        if image in images:
            raise ValueError(f"duplicate external image: {image}")
        images.append(image)
    return sorted(images)


def main() -> int:
    args = parse_args()
    try:
        build_inventory = load_inventory_builder()
        inventory = build_inventory(
            args.rendered.read_text(encoding="utf-8"), args.first_party_repository
        )
        expected = read_allowlist(args.allowlist, args.first_party_repository)
        actual = sorted(inventory["externalImages"])
        if actual != expected:
            missing = sorted(set(actual) - set(expected))
            stale = sorted(set(expected) - set(actual))
            raise ValueError(f"external image set mismatch; missing={missing}, stale={stale}")
        result: dict[str, Any] = {
            "schemaVersion": 1,
            "firstPartyRepository": args.first_party_repository,
            "externalImageCount": len(actual),
            "images": actual,
        }
        if args.output:
            args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
    except (OSError, ValueError, yaml.YAMLError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
