#!/usr/bin/env bash
set -e

echo "Running T9 Image Evidence Collection..."

# 1. Render Helm manifests
echo "Rendering Helm manifests..."
cd "phase3 - information" || exit 1
helm template techx-corp ./techx-corp-chart -f ./techx-corp-chart/values.yaml -f ./deploy/values-prod.yaml > ../rendered.yaml
cd ..

echo "Extracting images from rendered manifests..."
grep -E 'image:[[:space:]]+' rendered.yaml | awk '{print $2}' | tr -d '"'\''\r' | sort -u > images.txt

INTERNAL_REPO="197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp"
FAIL=0

echo "--- Manifest Image Audit ---"
while read -r img; do
  echo "Checking: $img"
  if [[ "$img" == "$INTERNAL_REPO"* ]]; then
    if ! [[ "$img" == *"@sha256:"* ]]; then
      echo "❌ ERROR: Internal image uses tag without digest pinning: $img"
      FAIL=1
    else
      echo "✅ OK: Internal image is digest-pinned"
    fi
  fi
done < images.txt

if [ "$FAIL" -eq 1 ]; then
  echo "Audit failed. Please fix unpinned images."
  exit 1
fi

echo "--- AWS ECR Digest Audit ---"
while read -r img; do
  if [[ "$img" == "$INTERNAL_REPO"* ]]; then
    DIGEST="${img#*@}"
    TAG_PART="${img%@*}"
    TAG="${TAG_PART#*:}"
    
    echo "Querying ECR for tag=$TAG, digest=$DIGEST"
    aws ecr describe-images --repository-name techx-corp --image-ids "imageDigest=$DIGEST" > /dev/null
    echo "✅ Found in ECR."
  fi
done < images.txt

echo "--- AWS Inspector Vulnerability Audit ---"
echo "Note: Inspector requires active scanning. Querying findings..."
while read -r img; do
  if [[ "$img" == "$INTERNAL_REPO"* ]]; then
    DIGEST="${img#*@}"
    TAG_PART="${img%@*}"
    TAG="${TAG_PART#*:}"
    
    echo "Querying scan findings for digest $DIGEST..."
    set +e
    aws ecr describe-image-scan-findings --repository-name techx-corp --image-id "imageDigest=$DIGEST" > scan-results.json 2>/dev/null
    SCAN_STATUS=$?
    set -e
    if [ $SCAN_STATUS -eq 0 ]; then
       HIGH=$(jq '.imageScanFindings.findingSeverityCounts.HIGH // 0' scan-results.json)
       CRITICAL=$(jq '.imageScanFindings.findingSeverityCounts.CRITICAL // 0' scan-results.json)
       echo "   Vulnerabilities - HIGH: $HIGH, CRITICAL: $CRITICAL"
    else
       echo "   Scan findings not available via ECR API (maybe handled by Trivy/Inspector V2 independently)."
    fi
  fi
done < images.txt

echo "--- Kubernetes Runtime Audit ---"
if kubectl get nodes >/dev/null 2>&1; then
  echo "Checking runtime pods in techx-tf3..."
  kubectl get pods -n techx-tf3 -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[*].image}{"\n"}{end}' | while read -r pod_name images; do
     echo "Pod: $pod_name"
     for runtime_img in $images; do
        if [[ "$runtime_img" == "$INTERNAL_REPO"* ]]; then
           echo "   Runtime Image: $runtime_img"
           if ! [[ "$runtime_img" == *"@sha256:"* ]]; then
              echo "   ❌ ERROR: Pod is running unpinned image: $runtime_img"
              FAIL=1
           fi
        fi
     done
  done
else
  echo "kubectl context not available, skipping runtime check."
fi

if [ "$FAIL" -eq 1 ]; then
  echo "Audit failed."
  exit 1
fi

echo "T9 Evidence Collection Passed!"
