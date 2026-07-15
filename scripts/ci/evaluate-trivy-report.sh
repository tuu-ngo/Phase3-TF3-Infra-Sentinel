#!/usr/bin/env bash
set -e

# evaluate-trivy-report.sh
# Reads image-digests.tsv and determines if the CI pipeline should fail.
# Writes a markdown summary to summary.md.

# Run from the root of the repo (or from workflow dir where it is called)
# The workflow executes: ../../scripts/ci/evaluate-trivy-report.sh from inside techx-corp-platform
cd "phase3 - information/techx-corp-platform" 2>/dev/null || true

if [ ! -f image-digests.tsv ]; then
  echo "Error: image-digests.tsv not found!" >&2
  exit 1
fi

FAIL_BUILD=0
SUMMARY_FILE="summary.md"

echo "# Trivy Security Scan Summary" > "$SUMMARY_FILE"
echo "" >> "$SUMMARY_FILE"
echo "| Service | Platform | CRITICAL | HIGH | Status |" >> "$SUMMARY_FILE"
echo "|---------|----------|----------|------|--------|" >> "$SUMMARY_FILE"

# Read the file line by line, skipping the header
while IFS=$'\t' read -r svc tag digest plat crit high; do
  if [ "$svc" = "service" ]; then continue; fi # Skip header
  
  STATUS="✅ PASS"
  
  # Ensure crit and high are integers, if empty or invalid, fail build
  if ! [[ "$crit" =~ ^[0-9]+$ ]]; then crit="ERR"; STATUS="❌ ERROR"; fi
  if ! [[ "$high" =~ ^[0-9]+$ ]]; then high="ERR"; STATUS="❌ ERROR"; fi
  
  if [ "$crit" != "ERR" ] && [ "$high" != "ERR" ]; then
    if [ "$crit" -gt 0 ] || [ "$high" -gt 0 ]; then
      STATUS="❌ FAIL"
    fi
  fi
  
  if [ "$STATUS" != "✅ PASS" ]; then
    FAIL_BUILD=1
  fi
  
  echo "| $svc | $plat | $crit | $high | $STATUS |" >> "$SUMMARY_FILE"
done < image-digests.tsv

echo "" >> "$SUMMARY_FILE"
if [ "$FAIL_BUILD" -eq 1 ]; then
  echo "## Result: ❌ FAILED" >> "$SUMMARY_FILE"
  echo "One or more images contain HIGH or CRITICAL vulnerabilities. Please check the artifacts for details." >> "$SUMMARY_FILE"
  exit 1
else
  echo "## Result: ✅ PASSED" >> "$SUMMARY_FILE"
  echo "No HIGH or CRITICAL vulnerabilities found." >> "$SUMMARY_FILE"
  exit 0
fi
