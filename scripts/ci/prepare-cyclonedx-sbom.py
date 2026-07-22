#!/usr/bin/env python3
"""Validate and enrich a CycloneDX SBOM before Cosign attestation."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REQUIRED_PROPERTIES = {
    "techx.image",
    "techx.platform",
    "techx.sourceSha",
    "techx.subjectDigest",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--image", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--subject-digest", required=True)
    parser.add_argument("--source-sha", required=True)
    return parser.parse_args()


def fail(message: str) -> None:
    raise ValueError(message)


def property_map(properties: Any) -> dict[str, str]:
    if not isinstance(properties, list):
        fail("metadata.properties must be a list")
    result: dict[str, str] = {}
    for item in properties:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            fail("metadata.properties entries must contain a string name")
        if item["name"] in result:
            fail(f"duplicate SBOM property: {item['name']}")
        result[item["name"]] = str(item.get("value", ""))
    return result


def prepare(document: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    if document.get("bomFormat") != "CycloneDX":
        fail("bomFormat must be CycloneDX")
    if not isinstance(document.get("specVersion"), str) or not document["specVersion"]:
        fail("specVersion must be present")
    if not isinstance(document.get("components"), list):
        fail("components must be a list")
    metadata = document.get("metadata")
    if not isinstance(metadata, dict):
        fail("metadata must be present")
    if not DIGEST_RE.fullmatch(args.subject_digest):
        fail("subject digest must be a lowercase sha256 digest")
    if not args.platform.startswith("linux/"):
        fail("platform must use the linux/<arch> form")
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_sha):
        fail("source SHA must be a 40-character lowercase hexadecimal SHA")

    existing = property_map(metadata.get("properties", []))
    if any(name in existing for name in REQUIRED_PROPERTIES):
        fail("input SBOM already contains a reserved TechX property")

    metadata["properties"] = [
        *metadata.get("properties", []),
        {"name": "techx.image", "value": args.image},
        {"name": "techx.platform", "value": args.platform},
        {"name": "techx.sourceSha", "value": args.source_sha},
        {"name": "techx.subjectDigest", "value": args.subject_digest},
    ]
    return document


def main() -> int:
    args = parse_args()
    try:
        document = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            fail("SBOM root must be an object")
        prepared = prepare(document, args)
        args.output.write_text(json.dumps(prepared, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"bomFormat": prepared["bomFormat"], "specVersion": prepared["specVersion"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
