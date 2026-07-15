#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
WORK_DIR="${TRIVY_WORK_DIR:-${REPO_ROOT}/phase3 - information/techx-corp-platform}"

cd "$WORK_DIR" || exit 1

if [ ! -f image-digests.tsv ]; then
  echo "Error: image-digests.tsv not found in $WORK_DIR!" >&2
  exit 1
fi

FAIL_BUILD=0
SUMMARY_FILE="summary.md"

echo "# Trivy Security Scan Summary" > "$SUMMARY_FILE"
echo "" >> "$SUMMARY_FILE"
echo "| Service | Platform | CRITICAL | HIGH | Status |" >> "$SUMMARY_FILE"
echo "|---------|----------|----------|------|--------|" >> "$SUMMARY_FILE"

# Read the file line by line, skipping the header
while IFS=$'\t' read -r svc tag digest plat workflow_status || [ -n "$svc" ]; do
  # Skip header or empty lines
  if [ -z "$svc" ] || [ "$svc" = "service" ]; then continue; fi
  
  # Remove potential \r from workflow_status
  workflow_status=$(echo "$workflow_status" | tr -d '\r')
  plat_safe=$(echo "$plat" | tr '/' '-')
  report_file="reports/${svc}-${plat_safe}.json"
  STATUS="✅ PASS"
  
  if [ "$workflow_status" == "ERR" ]; then
     crit="ERR"
     high="ERR"
     STATUS="❌ SCAN_ERR"
     FAIL_BUILD=1
  elif [ ! -f "$report_file" ]; then
     crit="ERR"
     high="ERR"
     STATUS="❌ MISSING_REPORT"
     FAIL_BUILD=1
  else
     if ! jq -e . "$report_file" >/dev/null 2>&1; then
        crit="ERR"
        high="ERR"
        STATUS="❌ INVALID_JSON"
        FAIL_BUILD=1
     else
        has_results=$(jq -e 'has("Results")' "$report_file" >/dev/null 2>&1 && echo true || echo false)
        if [ "$has_results" != "true" ]; then
           crit="ERR"
           high="ERR"
           STATUS="❌ PARTIAL_EMPTY_REPORT"
           FAIL_BUILD=1
        else
           crit=$(jq '[.Results[]? | .Vulnerabilities[]? | select(.Severity=="CRITICAL")] | length' "$report_file")
           high=$(jq '[.Results[]? | .Vulnerabilities[]? | select(.Severity=="HIGH")] | length' "$report_file")
           
           if [ "$crit" -gt 0 ] || [ "$high" -gt 0 ]; then
             STATUS="❌ FAIL"
             FAIL_BUILD=1
           fi
        fi
     fi
  fi
  
  echo "| $svc | $plat | $crit | $high | $STATUS |" >> "$SUMMARY_FILE"
done < image-digests.tsv

echo "" >> "$SUMMARY_FILE"
if [ "$FAIL_BUILD" -eq 1 ]; then
  echo "## Result: ❌ FAILED" >> "$SUMMARY_FILE"
  echo "One or more images contain HIGH or CRITICAL vulnerabilities or scanner failed. Please check the artifacts." >> "$SUMMARY_FILE"
  exit 1
else
  echo "## Result: ✅ PASSED" >> "$SUMMARY_FILE"
  echo "No HIGH or CRITICAL vulnerabilities found." >> "$SUMMARY_FILE"
  exit 0
fi
