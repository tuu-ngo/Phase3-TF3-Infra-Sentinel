#!/usr/bin/env bash
set -euo pipefail

repository=""
region="ap-southeast-1"
base_tag=""
services=""
max_high=0
max_critical=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repository) repository="$2"; shift 2 ;;
    --region) region="$2"; shift 2 ;;
    --base-tag) base_tag="$2"; shift 2 ;;
    --services) services="$2"; shift 2 ;;
    --max-high) max_high="$2"; shift 2 ;;
    --max-critical) max_critical="$2"; shift 2 ;;
    *)
      echo "unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$repository" || -z "$base_tag" || -z "$services" ]]; then
  echo "usage: $0 --repository NAME --base-tag TAG --services \"svc1 svc2\" [--region REGION] [--max-high N] [--max-critical N]" >&2
  exit 2
fi

gate_one() {
  local service="$1"
  local tag="${base_tag}-${service}"
  local digest status

  echo "Checking scan status for ${repository}:${tag}"
  digest="$(aws ecr describe-images \
    --repository-name "$repository" \
    --region "$region" \
    --image-ids imageTag="$tag" \
    --query 'imageDetails[0].imageDigest' \
    --output text)"

  if [[ -z "$digest" || "$digest" == "None" ]]; then
    echo "missing image digest for ${tag}" >&2
    return 1
  fi

  for _ in {1..30}; do
    status="$(aws ecr describe-image-scan-findings \
      --repository-name "$repository" \
      --region "$region" \
      --image-id imageDigest="$digest" \
      --query 'imageScanStatus.status' \
      --output text 2>/dev/null || true)"
    if [[ "$status" == "COMPLETE" ]]; then
      break
    fi
    sleep 10
  done

  if [[ "$status" != "COMPLETE" ]]; then
    echo "scan did not reach COMPLETE for ${tag}" >&2
    return 1
  fi

  local high critical
  high="$(aws ecr describe-image-scan-findings \
    --repository-name "$repository" \
    --region "$region" \
    --image-id imageDigest="$digest" \
    --query 'imageScanFindings.findingSeverityCounts.HIGH' \
    --output text 2>/dev/null || echo 0)"
  critical="$(aws ecr describe-image-scan-findings \
    --repository-name "$repository" \
    --region "$region" \
    --image-id imageDigest="$digest" \
    --query 'imageScanFindings.findingSeverityCounts.CRITICAL' \
    --output text 2>/dev/null || echo 0)"

  high="${high:-0}"
  critical="${critical:-0}"
  [[ "$high" == "None" ]] && high=0
  [[ "$critical" == "None" ]] && critical=0

  if (( high > max_high || critical > max_critical )); then
    echo "scan gate failed for ${tag}: HIGH=${high} CRITICAL=${critical} (threshold HIGH<=${max_high}, CRITICAL<=${max_critical})" >&2
    return 1
  fi

  echo "scan gate passed for ${tag}: HIGH=${high} CRITICAL=${critical}"
}

for service in $services; do
  gate_one "$service"
done
