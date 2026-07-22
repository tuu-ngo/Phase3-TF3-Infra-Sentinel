#!/usr/bin/env python3
"""Retrieve and validate one trusted CycloneDX SBOM from an ECR image digest."""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


EXPECTED_REPOSITORY = "197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp"
EXPECTED_ISSUER = "https://token.actions.githubusercontent.com"
EXPECTED_IDENTITY = (
    "https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel/"
    ".github/workflows/build-push-ecr.yml@refs/heads/main"
)
CYCLONEDX_PREDICATE = "https://cyclonedx.org/bom"
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def load_resolver():
    path = Path(__file__).with_name("resolve-oci-platforms.py")
    spec = importlib.util.spec_from_file_location("resolve_oci_platforms", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load OCI platform resolver")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RESOLVER = load_resolver()


def fail(message: str) -> None:
    raise ValueError(message)


def parse_image(image: str) -> tuple[str, str]:
    if "@" not in image:
        fail("image must use an immutable @sha256 digest")
    repository, digest = image.rsplit("@", 1)
    if repository != EXPECTED_REPOSITORY or not DIGEST_RE.fullmatch(digest):
        fail(f"image must be {EXPECTED_REPOSITORY}@sha256:<64 lowercase hex>")
    return repository, digest


def run_capture(command: list[str], *, input_text: str | None = None) -> str:
    try:
        result = subprocess.run(
            command,
            input=input_text,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        fail(f"required command is unavailable: {command[0]}")
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip().splitlines()[-1] if exc.stderr.strip() else "no diagnostic"
        fail(f"command failed ({command[0]}): {detail}")
    return result.stdout


def authenticate_ecr(registry: str, region: str) -> None:
    password = run_capture(["aws", "ecr", "get-login-password", "--region", region])
    try:
        subprocess.run(
            ["docker", "login", registry, "--username", "AWS", "--password-stdin"],
            input=password,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        fail("required command is unavailable: docker")
    except subprocess.CalledProcessError:
        fail("docker login failed; ECR credentials were not accepted")


def manifest_for(image: str) -> dict[str, Any]:
    raw = run_capture(["docker", "buildx", "imagetools", "inspect", "--raw", image])
    try:
        document = json.loads(raw)
    except json.JSONDecodeError:
        fail("Buildx returned invalid image manifest JSON")
    if not isinstance(document, dict):
        fail("image manifest root must be an object")
    return document


def decode_payload(entry: dict[str, Any]) -> dict[str, Any]:
    payload = entry.get("payload")
    if not isinstance(payload, str) or not payload:
        fail("Cosign attestation has no DSSE payload")
    try:
        decoded = base64.b64decode(payload + "=" * (-len(payload) % 4), validate=False)
        statement = json.loads(decoded)
    except (ValueError, json.JSONDecodeError) as exc:
        fail(f"Cosign DSSE payload is not valid JSON: {exc}")
    if not isinstance(statement, dict):
        fail("in-toto statement must be an object")
    return statement


def parse_cosign_output(raw: str) -> list[dict[str, Any]]:
    try:
        document = json.loads(raw)
        entries = document if isinstance(document, list) else [document]
    except json.JSONDecodeError:
        entries = []
        for line in raw.splitlines():
            if line.strip():
                entries.append(json.loads(line))
    if not entries or not all(isinstance(entry, dict) for entry in entries):
        fail("Cosign returned no usable attestation records")
    return entries


def property_map(predicate: Any) -> dict[str, str]:
    if not isinstance(predicate, dict):
        fail("attestation predicate must be an object")
    metadata = predicate.get("metadata")
    if not isinstance(metadata, dict):
        fail("SBOM metadata must be an object")
    properties = metadata.get("properties")
    if not isinstance(properties, list):
        fail("SBOM metadata.properties must be a list")
    result: dict[str, str] = {}
    for item in properties:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            fail("SBOM metadata.properties entries must have a name")
        name = item["name"]
        if name in result:
            fail(f"duplicate SBOM property: {name}")
        result[name] = str(item.get("value", ""))
    return result


def subject_matches(statement: dict[str, Any], child_digest: str) -> bool:
    subjects = statement.get("subject")
    if not isinstance(subjects, list) or len(subjects) != 1:
        return False
    digest = subjects[0].get("digest") if isinstance(subjects[0], dict) else None
    return isinstance(digest, dict) and digest.get("sha256") == child_digest.removeprefix("sha256:")


def validate_candidate(
    statement: dict[str, Any],
    child_digest: str,
    expected_index_digest: str | None,
    expected_platform: str | None,
) -> dict[str, Any]:
    if statement.get("predicateType") != CYCLONEDX_PREDICATE:
        fail("attestation predicate type is not CycloneDX")
    predicate = statement.get("predicate")
    if not isinstance(predicate, dict):
        fail("CycloneDX predicate is missing")
    if predicate.get("bomFormat") != "CycloneDX":
        fail("SBOM bomFormat is not CycloneDX")
    components = predicate.get("components")
    if not isinstance(components, list) or not components:
        fail("SBOM components must be non-empty")
    for component in components:
        if (
            not isinstance(component, dict)
            or not isinstance(component.get("type"), str)
            or not component["type"].strip()
            or not isinstance(component.get("name"), str)
            or not component["name"].strip()
        ):
            fail("SBOM components must contain meaningful type and name")
    if not subject_matches(statement, child_digest):
        fail("attestation subject digest does not match the runtime child digest")

    properties = property_map(predicate)
    required = {
        "techx.image",
        "techx.indexDigest",
        "techx.platform",
        "techx.sourceSha",
        "techx.subjectDigest",
    }
    missing = sorted(required - properties.keys())
    if missing:
        fail("SBOM is missing TechX properties: " + ", ".join(missing))
    if properties["techx.subjectDigest"] != child_digest:
        fail("techx.subjectDigest does not match the runtime child digest")
    if not DIGEST_RE.fullmatch(properties["techx.indexDigest"]):
        fail("techx.indexDigest is not a valid lowercase sha256 digest")
    if expected_index_digest and properties["techx.indexDigest"] != expected_index_digest:
        fail("techx.indexDigest does not match the requested image index")
    if not SOURCE_SHA_RE.fullmatch(properties["techx.sourceSha"]):
        fail("techx.sourceSha is not a 40-character lowercase SHA")
    if not properties["techx.image"].endswith("@" + child_digest):
        fail("techx.image does not identify the runtime child digest")
    if expected_platform and properties["techx.platform"] != expected_platform:
        fail("SBOM platform does not match --platform")
    return predicate


def select_sbom(
    entries: list[dict[str, Any]],
    *,
    child_digest: str,
    expected_index_digest: str | None,
    expected_platform: str | None,
) -> dict[str, Any]:
    valid: list[dict[str, Any]] = []
    errors: list[str] = []
    for entry in entries:
        try:
            statement = decode_payload(entry)
            predicate = validate_candidate(
                statement, child_digest, expected_index_digest, expected_platform
            )
            valid.append(predicate)
        except ValueError as exc:
            errors.append(str(exc))
    if len(valid) == 0:
        detail = errors[0] if errors else "no matching attestation"
        fail("no valid current CycloneDX SBOM attestation: " + detail)
    if len(valid) > 1:
        fail("ambiguous: more than one valid current CycloneDX SBOM attestation")
    return valid[0]


def cosign_verify_command(image: str) -> list[str]:
    return [
        "cosign",
        "verify-attestation",
        "--output",
        "json",
        "--type",
        "cyclonedx",
        "--certificate-oidc-issuer",
        EXPECTED_ISSUER,
        "--certificate-identity",
        EXPECTED_IDENTITY,
        image,
    ]


def retrieve(image: str, platform: str | None, region: str, login: bool) -> dict[str, Any]:
    repository, requested_digest = parse_image(image)
    registry = repository.split("/", 1)[0]
    if login:
        authenticate_ecr(registry, region)

    manifest = manifest_for(image)
    expected_index_digest: str | None = None
    if manifest.get("mediaType") in RESOLVER.INDEX_MEDIA_TYPES:
        expected_index_digest = requested_digest
        runnable = sorted(
            {
                RESOLVER.descriptor_platform(descriptor)
                for descriptor in manifest.get("manifests", [])
                if isinstance(descriptor, dict)
            }
            - {None}
        )
        linux_platforms = [platform_name for platform_name in runnable if platform_name.startswith("linux/")]
        if platform is None:
            if len(linux_platforms) != 1:
                fail("multi-platform index requires --platform linux/<arch>")
            platform = linux_platforms[0]
        if platform not in linux_platforms:
            fail(f"requested platform is not present in index: {platform}")

        # The release resolver remains strict: resolve every runnable Linux
        # child first, then select the operator-requested platform. This keeps
        # release validation fail-closed without making retrieval reject the
        # other valid platforms in the same index.
        mapping = RESOLVER.resolve(manifest, image, linux_platforms)
        matches = [entry for entry in mapping["platforms"] if entry["platform"] == platform]
        if len(matches) != 1:
            fail(f"unable to resolve exactly one child for {platform}")
        child = matches[0]
        child_digest = child["digest"]
        child_image = child["image"]
    else:
        child_digest = requested_digest
        child_image = image

    raw = run_capture(cosign_verify_command(child_image))
    predicate = select_sbom(
        parse_cosign_output(raw),
        child_digest=child_digest,
        expected_index_digest=expected_index_digest,
        expected_platform=platform,
    )
    return {
        "image": image,
        "indexDigest": expected_index_digest or property_map(predicate)["techx.indexDigest"],
        "childImage": child_image,
        "childDigest": child_digest,
        "platform": property_map(predicate)["techx.platform"],
        "predicateType": CYCLONEDX_PREDICATE,
        "predicate": predicate,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("image")
    parser.add_argument("--platform")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--region", default="ap-southeast-1")
    parser.add_argument("--no-login", action="store_true")
    parser.add_argument("--metadata", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = retrieve(args.image, args.platform, args.region, not args.no_login)
        output: Any = result if args.metadata else result["predicate"]
        encoded = json.dumps(output, indent=2) + "\n"
        if args.output:
            args.output.write_text(encoded, encoding="utf-8")
        else:
            sys.stdout.write(encoded)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
