#!/usr/bin/env python3
"""Fail-closed verifier for immutable GitHub Actions and Dockerfile bases."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_ROOT = ROOT / ".github" / "workflows"
DOCKER_ROOT = ROOT / "phase3 - information" / "techx-corp-platform"
SCOPE_FILE = ROOT / "scripts" / "ci" / "dockerfile-scope.json"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
USES_RE = re.compile(r"^(?P<indent>\s*)(?:-\s*)?uses:\s*(?P<value>\S+)(?:\s+#\s*(?P<version>\S+))?\s*$")
ARG_RE = re.compile(r"^ARG\s+([A-Za-z_][A-Za-z0-9_]*)(?:=(.*))?$", re.I)
FROM_RE = re.compile(r"^FROM\s+(?:(--platform=\S+)\s+)?(\S+)(?:\s+AS\s+(\S+))?\s*$", re.I)
VAR_RE = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")
FLOATING_REMOTE = ("/main/", "/master/", "/releases/latest/", "@latest")


@dataclass(frozen=True)
class DockerRef:
    path: str
    line: int
    raw_from: str
    resolved_image: str
    stage: str | None
    platform_expression: str | None
    classification: str
    owner: str
    expected_platforms: list[str]


def fail(errors: list[str]) -> int:
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    return 1


def workflow_paths() -> list[Path]:
    return sorted([*WORKFLOW_ROOT.glob("*.yml"), *WORKFLOW_ROOT.glob("*.yaml")])


def verify_workflows() -> list[str]:
    errors: list[str] = []
    for path in workflow_paths():
        text = path.read_text(encoding="utf-8")
        for token in FLOATING_REMOTE:
            if token in text:
                errors.append(f"{path.relative_to(ROOT)} contains floating remote dependency {token}")
        for number, line in enumerate(text.splitlines(), 1):
            match = USES_RE.match(line)
            if not match:
                continue
            value = match.group("value")
            if value.startswith("./") or value.startswith("docker://"):
                continue
            if "@" not in value:
                errors.append(f"{path.relative_to(ROOT)}:{number}: external uses has no ref: {value}")
                continue
            ref = value.rsplit("@", 1)[1]
            if not SHA_RE.fullmatch(ref):
                errors.append(f"{path.relative_to(ROOT)}:{number}: external uses is not a full SHA: {value}")
            version = match.group("version")
            if not version or not re.fullmatch(r"v?[0-9][A-Za-z0-9._+-]*", version):
                errors.append(f"{path.relative_to(ROOT)}:{number}: SHA pin needs a version comment")
    return errors


def dockerfile_paths() -> list[Path]:
    return sorted(
        path
        for path in DOCKER_ROOT.rglob("*")
        if path.is_file()
        and (path.name == "Dockerfile" or path.name.startswith("Dockerfile.") or path.name.endswith(".Dockerfile"))
    )


def logical_lines(path: Path) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    buffer = ""
    start = 0
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = raw.strip()
        if not buffer and (not stripped or stripped.startswith("#")):
            continue
        if not buffer:
            start = number
        if stripped.endswith("\\"):
            buffer += stripped[:-1].strip() + " "
            continue
        buffer += stripped
        result.append((start, buffer.strip()))
        buffer = ""
    if buffer:
        result.append((start, buffer.strip()))
    return result


def resolve_vars(value: str, args: dict[str, str], *, path: Path, line: int) -> str:
    seen: set[str] = set()
    current = value
    for _ in range(32):
        names = [left or right for left, right in VAR_RE.findall(current)]
        if not names:
            return current.strip('"\'')
        for name in names:
            if name in seen:
                raise ValueError(f"{path.relative_to(ROOT)}:{line}: cyclic ARG reference: {name}")
            if name not in args or not args[name]:
                raise ValueError(f"{path.relative_to(ROOT)}:{line}: unresolved ARG in FROM: {name}")
            seen.add(name)
            current = re.sub(rf"\$(?:\{{{re.escape(name)}\}}|{re.escape(name)}\b)", args[name], current)
    raise ValueError(f"{path.relative_to(ROOT)}:{line}: ARG expansion exceeded limit")


def load_scope(paths: list[Path]) -> tuple[dict[str, dict], list[str]]:
    errors: list[str] = []
    try:
        document = json.loads(SCOPE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [f"cannot read {SCOPE_FILE.relative_to(ROOT)}: {exc}"]
    entries = document.get("dockerfiles") if isinstance(document, dict) else None
    if not isinstance(entries, list):
        return {}, ["dockerfile-scope.json must contain a dockerfiles list"]
    mapped: dict[str, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            errors.append("dockerfile scope entry must contain a string path")
            continue
        key = entry["path"]
        if key in mapped:
            errors.append(f"duplicate Dockerfile scope mapping: {key}")
        mapped[key] = entry
        if entry.get("classification") not in {"production", "test", "tooling", "excluded"}:
            errors.append(f"invalid classification for {key}")
        if not entry.get("owner"):
            errors.append(f"missing owner for {key}")
        if entry.get("inScope") is not True:
            errors.append(f"PM-129 requires every discovered Dockerfile in scope: {key}")
        platforms = entry.get("expectedPlatforms")
        if not isinstance(platforms, list) or not platforms:
            errors.append(f"missing expectedPlatforms for {key}")
    discovered = {str(path.relative_to(ROOT)) for path in paths}
    mapped_paths = set(mapped)
    for missing in sorted(discovered - mapped_paths):
        errors.append(f"Dockerfile missing scope mapping: {missing}")
    for stale in sorted(mapped_paths - discovered):
        errors.append(f"stale Dockerfile scope mapping: {stale}")
    return mapped, errors


def parse_dockerfiles() -> tuple[list[DockerRef], list[str]]:
    paths = dockerfile_paths()
    scope, errors = load_scope(paths)
    refs: list[DockerRef] = []
    for path in paths:
        relative = str(path.relative_to(ROOT))
        entry = scope.get(relative, {})
        args: dict[str, str] = {}
        stages: set[str] = set()
        for line, logical in logical_lines(path):
            arg_match = ARG_RE.match(logical)
            if arg_match:
                name, value = arg_match.groups()
                if value is not None:
                    try:
                        args[name] = resolve_vars(value.strip(), args, path=path, line=line)
                    except ValueError as exc:
                        errors.append(str(exc))
                continue
            from_match = FROM_RE.match(logical)
            if not from_match:
                continue
            platform_expr, raw_image, stage = from_match.groups()
            # A stage reference may contain TARGETARCH or another automatic
            # build argument. It is not an external registry image, so it is
            # safe to skip it before attempting ARG resolution.
            raw_lower = raw_image.lower()
            if raw_lower == "scratch" or ("/" not in raw_image and ":" not in raw_image and "@" not in raw_image):
                if stage:
                    stages.add(stage.lower())
                continue
            try:
                image = resolve_vars(raw_image, args, path=path, line=line)
            except ValueError as exc:
                errors.append(str(exc))
                continue
            lower = image.lower()
            if lower == "scratch" or lower in stages:
                if stage:
                    stages.add(stage.lower())
                continue
            if "@" not in image:
                errors.append(f"{relative}:{line}: external FROM lacks digest: {image}")
            else:
                readable, digest = image.rsplit("@", 1)
                if not DIGEST_RE.fullmatch(digest):
                    errors.append(f"{relative}:{line}: invalid digest: {digest}")
                last_component = readable.rsplit("/", 1)[-1]
                if ":" not in last_component:
                    errors.append(f"{relative}:{line}: pinned FROM must preserve a readable tag: {image}")
            refs.append(
                DockerRef(
                    path=relative,
                    line=line,
                    raw_from=raw_image,
                    resolved_image=image,
                    stage=stage,
                    platform_expression=platform_expr,
                    classification=str(entry.get("classification", "")),
                    owner=str(entry.get("owner", "")),
                    expected_platforms=list(entry.get("expectedPlatforms", [])),
                )
            )
            if stage:
                stages.add(stage.lower())
    return refs, errors


def registry_manifest(ref: str) -> dict:
    command = ["docker", "buildx", "imagetools", "inspect", ref, "--format", "{{json .Manifest}}"]
    completed = subprocess.run(command, check=True, text=True, capture_output=True)
    return json.loads(completed.stdout)


def verify_registry(refs: list[DockerRef]) -> list[str]:
    errors: list[str] = []
    checked: set[tuple[str, tuple[str, ...]]] = set()
    for item in refs:
        key = (item.resolved_image, tuple(sorted(item.expected_platforms)))
        if key in checked:
            continue
        checked.add(key)
        if "@" not in item.resolved_image:
            continue
        tag_ref, expected_digest = item.resolved_image.rsplit("@", 1)
        try:
            tag_manifest = registry_manifest(tag_ref)
            if tag_manifest.get("digest") != expected_digest:
                errors.append(
                    f"{tag_ref}: tag resolves to {tag_manifest.get('digest')}, pin expects {expected_digest}"
                )
            raw = subprocess.run(
                ["docker", "buildx", "imagetools", "inspect", "--raw", item.resolved_image],
                check=True,
                text=True,
                capture_output=True,
            ).stdout
            manifest = json.loads(raw)
            descriptors = manifest.get("manifests", [])
            present = {
                f"{descriptor.get('platform', {}).get('os')}/{descriptor.get('platform', {}).get('architecture')}"
                for descriptor in descriptors
                if isinstance(descriptor, dict) and isinstance(descriptor.get("platform"), dict)
            }
            if len(item.expected_platforms) > 1:
                missing = set(item.expected_platforms) - present
                if missing:
                    errors.append(f"{item.resolved_image}: missing platforms {sorted(missing)}")
        except (FileNotFoundError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
            errors.append(f"cannot verify registry reference {item.resolved_image}: {exc}")
    return errors


def git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, text=True, capture_output=True
        ).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflows", action="store_true")
    parser.add_argument("--dockerfiles", action="store_true")
    parser.add_argument("--list-refs", action="store_true")
    parser.add_argument("--verify-registry", action="store_true")
    parser.add_argument("--inventory-output", type=Path)
    args = parser.parse_args()
    run_workflows = args.workflows or not (args.workflows or args.dockerfiles)
    run_dockerfiles = args.dockerfiles or not (args.workflows or args.dockerfiles)
    errors: list[str] = []
    refs: list[DockerRef] = []
    if run_workflows:
        errors.extend(verify_workflows())
    if run_dockerfiles:
        refs, docker_errors = parse_dockerfiles()
        errors.extend(docker_errors)
        if args.verify_registry:
            errors.extend(verify_registry(refs))
    if args.list_refs:
        for ref in sorted({item.resolved_image for item in refs}):
            print(ref)
    if args.inventory_output:
        document = {
            "schemaVersion": 1,
            "baselineSha": git_sha(),
            "dockerfiles": len(dockerfile_paths()),
            "externalStages": [asdict(item) for item in refs],
        }
        args.inventory_output.parent.mkdir(parents=True, exist_ok=True)
        args.inventory_output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    if errors:
        return fail(errors)
    print(f"PASS: immutable pins verified ({len(workflow_paths())} workflows, {len(dockerfile_paths())} Dockerfiles)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
