#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
MODE="${1:---check}"

case "$MODE" in
  --check)
    exec python3 "$ROOT/scripts/ci/verify-immutable-pins.py" --workflows
    ;;
  --write)
    python3 - "$ROOT" <<'PY'
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

root = Path(sys.argv[1])
pattern = re.compile(r"^(?P<prefix>\s*(?:-\s*)?uses:\s*)(?P<target>\S+)(?P<suffix>.*)$")
sha_re = re.compile(r"^[0-9a-f]{40}$")
occurrences = []

for path in sorted([*(root / ".github/workflows").glob("*.yml"), *(root / ".github/workflows").glob("*.yaml")]):
    output = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        match = pattern.match(line)
        if not match:
            output.append(line)
            continue
        target = match.group("target")
        if target.startswith("./") or target.startswith("docker://"):
            output.append(line)
            continue
        if "@" not in target:
            raise SystemExit(f"FAIL: {path}:{number}: uses has no ref")
        action, ref = target.rsplit("@", 1)
        version = ref
        sha = ref
        if not sha_re.fullmatch(ref):
            if subprocess.run(["bash", "-lc", "command -v gh"], capture_output=True).returncode != 0:
                raise SystemExit("FAIL: gh is required to resolve a floating action ref")
            repo = "/".join(action.split("/")[:2])
            sha = subprocess.run(
                ["gh", "api", f"repos/{repo}/commits/{ref}", "--jq", ".sha"],
                check=True, text=True, capture_output=True,
            ).stdout.strip()
            if not sha_re.fullmatch(sha):
                raise SystemExit(f"FAIL: {action}@{ref} did not resolve to a commit SHA")
            line = f"{match.group('prefix')}{action}@{sha}  # {version}"
        else:
            comment = match.group("suffix").strip()
            version = comment.removeprefix("#").strip()
            if not version:
                raise SystemExit(f"FAIL: {path}:{number}: existing SHA pin has no version comment")
        occurrences.append({
            "workflow": str(path.relative_to(root)), "line": number, "action": action,
            "version": version, "sha": sha,
        })
        output.append(line)
    path.write_text("\n".join(output) + "\n")

lock = {
    "schemaVersion": 1,
    "resolvedAt": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),
    "occurrences": occurrences,
}
(root / "scripts/ci/action-pins.lock.json").write_text(json.dumps(lock, indent=2) + "\n")
PY
    exec python3 "$ROOT/scripts/ci/verify-immutable-pins.py" --workflows
    ;;
  *)
    echo "Usage: scripts/ci/pin-actions.sh [--check|--write]" >&2
    exit 2
    ;;
esac
