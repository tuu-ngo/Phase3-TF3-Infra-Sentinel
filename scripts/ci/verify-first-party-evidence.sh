#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
GET_SBOM="$SCRIPT_DIR/get-sbom.sh"

VALID_IMAGE=""
UNSIGNED_IMAGE=""
WRONG_ISSUER_IMAGE=""
WRONG_IDENTITY_IMAGE=""
MISSING_SBOM_IMAGE=""
WRONG_PREDICATE_IMAGE=""
TAGGED_IMAGE=""

usage() {
  cat >&2 <<'EOF'
Usage: verify-first-party-evidence.sh \
  --valid-image IMAGE \
  --unsigned-image IMAGE \
  --wrong-issuer-image IMAGE \
  --wrong-identity-image IMAGE \
  --missing-sbom-image IMAGE \
  --wrong-predicate-image IMAGE \
  --tagged-image IMAGE
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --valid-image) VALID_IMAGE="${2:?missing value}"; shift 2 ;;
    --unsigned-image) UNSIGNED_IMAGE="${2:?missing value}"; shift 2 ;;
    --wrong-issuer-image) WRONG_ISSUER_IMAGE="${2:?missing value}"; shift 2 ;;
    --wrong-identity-image) WRONG_IDENTITY_IMAGE="${2:?missing value}"; shift 2 ;;
    --missing-sbom-image) MISSING_SBOM_IMAGE="${2:?missing value}"; shift 2 ;;
    --wrong-predicate-image) WRONG_PREDICATE_IMAGE="${2:?missing value}"; shift 2 ;;
    --tagged-image) TAGGED_IMAGE="${2:?missing value}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "FAIL: unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

for value in \
  "$VALID_IMAGE" \
  "$UNSIGNED_IMAGE" \
  "$WRONG_ISSUER_IMAGE" \
  "$WRONG_IDENTITY_IMAGE" \
  "$MISSING_SBOM_IMAGE" \
  "$WRONG_PREDICATE_IMAGE" \
  "$TAGGED_IMAGE"; do
  [ -n "$value" ] || { echo "FAIL: all evidence fixture arguments are required" >&2; usage; exit 2; }
done

tmpdir="$(mktemp -d)"
trap 'rm -rf -- "$tmpdir"' EXIT

echo "Checking valid signed image and CycloneDX SBOM"
"$GET_SBOM" "$VALID_IMAGE" --metadata > "$tmpdir/valid.json"
python3 - "$tmpdir/valid.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    document = json.load(handle)
assert document["predicateType"] == "https://cyclonedx.org/bom"
assert document["predicate"]["bomFormat"] == "CycloneDX"
assert document["predicate"]["components"]
PY

expect_failure() {
  local name="$1"
  shift
  local log="$tmpdir/${name}.log"
  if "$@" >"$log" 2>&1; then
    echo "FAIL: ${name} unexpectedly succeeded" >&2
    cat "$log" >&2
    exit 1
  fi
  echo "Expected rejection: ${name}"
}

expect_failure unsigned "$GET_SBOM" "$UNSIGNED_IMAGE"
expect_failure wrong-issuer "$GET_SBOM" "$WRONG_ISSUER_IMAGE"
expect_failure wrong-identity "$GET_SBOM" "$WRONG_IDENTITY_IMAGE"
expect_failure missing-sbom "$GET_SBOM" "$MISSING_SBOM_IMAGE"
expect_failure wrong-predicate "$GET_SBOM" "$WRONG_PREDICATE_IMAGE"
expect_failure first-party-tag "$GET_SBOM" "$TAGGED_IMAGE"

echo "PM-127 first-party evidence matrix passed"
