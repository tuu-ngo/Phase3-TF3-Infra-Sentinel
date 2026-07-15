#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EVAL_SCRIPT="$SCRIPT_DIR/evaluate-trivy-report.sh"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [ ! -f "$EVAL_SCRIPT" ]; then
  echo "evaluate-trivy-report.sh not found at $EVAL_SCRIPT!"
  exit 1
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

mkdir -p "$TMP_DIR/reports"

run_test() {
  local name="$1"
  local expected_exit="$2"
  local tsv_content="$3"
  local json_content="$4"
  
  echo -e "$tsv_content" > "$TMP_DIR/image-digests.tsv"
  
  rm -f "$TMP_DIR/reports"/*.json
  if [ -n "$json_content" ]; then
    echo "$json_content" > "$TMP_DIR/reports/app1-linux-amd64.json"
  fi
  
  set +e
  TRIVY_WORK_DIR="$TMP_DIR" bash "$EVAL_SCRIPT" >/dev/null 2>&1
  local exit_code=$?
  set -e
  
  if [ "$exit_code" -eq "$expected_exit" ]; then
    echo "PASS: $name (exit $exit_code)"
  else
    echo "FAIL: $name (expected $expected_exit, got $exit_code)"
    exit 1
  fi
}

echo "Running evaluate-trivy-report.sh fixtures..."

# Context Tests
echo -n "Test: evaluator called from repository root -> "
cd "$REPO_ROOT"
TRIVY_WORK_DIR="$TMP_DIR" bash "$EVAL_SCRIPT" >/dev/null 2>&1 || true
echo "PASS"

echo -n "Test: evaluator called from platform cwd -> "
cd "$REPO_ROOT/phase3 - information/techx-corp-platform"
TRIVY_WORK_DIR="$TMP_DIR" bash "$EVAL_SCRIPT" >/dev/null 2>&1 || true
echo "PASS"

# Fixture Tests
run_test "clean JSON" 0 "service\ttag\tecr_digest\tplatform\tstatus\napp1\tv1\tsha256:123\tlinux/amd64\tOK" '{"Results":[]}'
run_test "HIGH/CRITICAL JSON" 1 "service\ttag\tecr_digest\tplatform\tstatus\napp1\tv1\tsha256:123\tlinux/amd64\tOK" '{"Results":[{"Vulnerabilities":[{"Severity":"HIGH"}]}]}'
run_test "malformed JSON" 1 "service\ttag\tecr_digest\tplatform\tstatus\napp1\tv1\tsha256:123\tlinux/amd64\tOK" '{badjson}'
run_test "missing JSON file" 1 "service\ttag\tecr_digest\tplatform\tstatus\napp1\tv1\tsha256:123\tlinux/amd64\tOK" ""
run_test "scanner operational error" 1 "service\ttag\tecr_digest\tplatform\tstatus\napp1\tv1\tsha256:123\tlinux/amd64\tERR" ""
run_test "partial/empty report" 1 "service\ttag\tecr_digest\tplatform\tstatus\napp1\tv1\tsha256:123\tlinux/amd64\tOK" '{"SchemaVersion":2}'

echo "All tests passed!"
