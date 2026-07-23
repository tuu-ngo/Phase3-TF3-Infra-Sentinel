#!/usr/bin/env python3
"""Build a canonical image inventory from a rendered Kubernetes manifest."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

import yaml


IMAGE_DIGEST_RE = re.compile(r"@sha256:[0-9a-f]{64}$")
POD_TEMPLATE_KINDS = {
    "DaemonSet",
    "Deployment",
    "Job",
    "ReplicaSet",
    "ReplicationController",
    "StatefulSet",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rendered", required=True, type=Path)
    parser.add_argument("--first-party-repository", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def pod_specs(document: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    kind = document.get("kind")
    if kind == "Pod":
        yield "pod", document.get("spec") or {}
        return

    if kind in POD_TEMPLATE_KINDS:
        yield "template", (document.get("spec") or {}).get("template", {}).get("spec") or {}
        return

    if kind == "CronJob":
        yield "template", (
            (document.get("spec") or {}).get("jobTemplate", {})
            .get("spec", {})
            .get("template", {})
            .get("spec")
            or {}
        )
        return

    if kind == "Rollout":
        spec = document.get("spec") or {}
        template = spec.get("template")
        if isinstance(template, dict):
            yield "template", template.get("spec") or {}


def container_entries(pod_spec: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    for container_type in ("containers", "initContainers", "ephemeralContainers"):
        containers = pod_spec.get(container_type) or []
        if not isinstance(containers, list):
            raise ValueError(f"{container_type} must be a list")
        for container in containers:
            if not isinstance(container, dict):
                raise ValueError(f"{container_type} entries must be objects")
            yield container_type, container


def is_first_party(image: str, repository: str) -> bool:
    return image.startswith(f"{repository}:") or image.startswith(f"{repository}@")


def build_inventory(rendered: str, repository: str) -> dict[str, Any]:
    images: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str]] = set()

    for document in yaml.safe_load_all(rendered):
        if not isinstance(document, dict):
            continue
        metadata = document.get("metadata") or {}
        for template_source, pod_spec in pod_specs(document):
            for container_type, container in container_entries(pod_spec):
                image = container.get("image")
                if not isinstance(image, str) or not image:
                    raise ValueError(
                        f"{document.get('kind')}/{metadata.get('name')} has a container without an image"
                    )
                identity = (
                    str(metadata.get("namespace") or "default"),
                    str(document.get("kind") or ""),
                    str(metadata.get("name") or ""),
                    container_type,
                    str(container.get("name") or ""),
                )
                if identity in seen:
                    raise ValueError(f"duplicate container identity: {identity}")
                seen.add(identity)
                images.append(
                    {
                        "namespace": str(metadata.get("namespace") or "default"),
                        "kind": str(document.get("kind") or ""),
                        "workload": str(metadata.get("name") or ""),
                        "templateSource": template_source,
                        "containerType": container_type,
                        "containerName": str(container.get("name") or ""),
                        "image": image,
                        "firstParty": is_first_party(image, repository),
                        "immutableDigest": bool(IMAGE_DIGEST_RE.search(image)),
                    }
                )

    images.sort(key=lambda item: (
        item["namespace"],
        item["kind"],
        item["workload"],
        item["containerType"],
        item["containerName"],
        item["image"],
    ))
    return {
        "schemaVersion": 1,
        "firstPartyRepository": repository,
        "imageCount": len(images),
        "firstPartyImages": sorted({item["image"] for item in images if item["firstParty"]}),
        "externalImages": sorted({item["image"] for item in images if not item["firstParty"]}),
        "images": images,
    }


def main() -> int:
    args = parse_args()
    try:
        inventory = build_inventory(args.rendered.read_text(encoding="utf-8"), args.first_party_repository)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    args.output.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"imageCount": inventory["imageCount"], "externalCount": len(inventory["externalImages"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
