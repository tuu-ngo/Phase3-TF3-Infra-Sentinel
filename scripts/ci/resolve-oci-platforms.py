#!/usr/bin/env python3
"""Resolve an immutable OCI image reference into deterministic platform digests."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
INDEX_MEDIA_TYPES = {
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
}
MANIFEST_MEDIA_TYPES = {
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
}


def fail(message: str) -> None:
    raise ValueError(message)


def parse_image(image: str) -> tuple[str, str]:
    if "@" not in image:
        fail("image must use an immutable @sha256 digest")
    repository, digest = image.rsplit("@", 1)
    if not repository or not DIGEST_RE.fullmatch(digest):
        fail("image must use an immutable lowercase @sha256 digest")
    return repository, digest


def parse_platforms(value: str) -> list[str]:
    platforms = [item.strip() for item in value.split(",") if item.strip()]
    if not platforms:
        fail("expected platforms must not be empty")
    if len(platforms) != len(set(platforms)):
        fail("expected platforms must be unique")
    for platform in platforms:
        if not re.fullmatch(r"linux/[a-z0-9_]+(?:/[a-z0-9_.-]+)?", platform):
            fail(f"invalid expected platform: {platform}")
    return platforms


def descriptor_platform(descriptor: dict[str, Any]) -> str | None:
    platform = descriptor.get("platform")
    if not isinstance(platform, dict):
        return None
    os_name = platform.get("os")
    architecture = platform.get("architecture")
    if not isinstance(os_name, str) or not isinstance(architecture, str):
        return None
    if os_name == "unknown" or architecture == "unknown":
        return None
    result = f"{os_name}/{architecture}"
    variant = platform.get("variant")
    if isinstance(variant, str) and variant:
        result += f"/{variant}"
    return result


def resolve(document: dict[str, Any], image: str, expected: list[str]) -> dict[str, Any]:
    repository, parent_digest = parse_image(image)
    media_type = document.get("mediaType")
    if media_type in MANIFEST_MEDIA_TYPES:
        if len(expected) != 1:
            fail("a single image manifest cannot satisfy multiple expected platforms")
        resolved = [{"platform": expected[0], "digest": parent_digest, "image": image}]
    elif media_type in INDEX_MEDIA_TYPES:
        manifests = document.get("manifests")
        if not isinstance(manifests, list):
            fail("image index manifests must be a list")
        by_platform: dict[str, list[str]] = {}
        for descriptor in manifests:
            if not isinstance(descriptor, dict):
                fail("image index manifest descriptors must be objects")
            platform = descriptor_platform(descriptor)
            if platform is None:
                continue
            digest = descriptor.get("digest")
            if not isinstance(digest, str) or not DIGEST_RE.fullmatch(digest):
                fail(f"platform {platform} has an invalid child digest")
            by_platform.setdefault(platform, []).append(digest)

        unexpected = sorted(
            platform
            for platform in by_platform
            if platform.startswith("linux/") and platform not in expected
        )
        if unexpected:
            fail("unexpected runnable platforms: " + ", ".join(unexpected))

        resolved = []
        for platform in expected:
            digests = by_platform.get(platform, [])
            if not digests:
                fail(f"missing child digest for {platform}")
            if len(digests) != 1:
                fail(f"ambiguous child digests for {platform}")
            digest = digests[0]
            resolved.append(
                {
                    "platform": platform,
                    "digest": digest,
                    "image": f"{repository}@{digest}",
                }
            )
    else:
        fail(f"unsupported manifest media type: {media_type!r}")

    return {
        "schemaVersion": 1,
        "image": image,
        "indexDigest": parent_digest,
        "mediaType": media_type,
        "platforms": resolved,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--image", required=True)
    parser.add_argument("--expected-platforms", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        document = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            fail("manifest root must be an object")
        result = resolve(document, args.image, parse_platforms(args.expected_platforms))
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"mediaType": result["mediaType"], "platforms": result["platforms"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
