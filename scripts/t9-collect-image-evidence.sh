#!/usr/bin/env bash
set -euo pipefail

export AWS_PROFILE="${AWS_PROFILE:-cdo1}"
export AWS_REGION="${AWS_REGION:-ap-southeast-1}"
NAMESPACE="${NAMESPACE:-techx-tf3}"
ALLOW_NO_KUBE="${ALLOW_NO_KUBE:-false}"

echo "Running T9 Image Evidence Collection..."

# 1. Render Helm manifests
echo "Rendering Helm manifests..."
cd "phase3 - information"
helm template techx-corp ./techx-corp-chart \
  --namespace "$NAMESPACE" \
  -f ./techx-corp-chart/values.yaml \
  -f ./deploy/values-flagd-sync.yaml \
  -f ./deploy/values-prod.yaml > ../rendered.yaml
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

echo "--- AWS ECR Digest Audit ---"
while read -r img; do
  if [[ "$img" == "$INTERNAL_REPO"* ]]; then
    DIGEST="${img#*@}"
    TAG_PART="${img%@*}"
    TAG="${TAG_PART#*:}"
    
    echo "Querying ECR for tag=$TAG, digest=$DIGEST"
    if ! aws ecr describe-images --repository-name techx-corp --image-ids "imageDigest=$DIGEST" > /dev/null 2>&1; then
      echo "❌ ERROR: Digest $DIGEST not found in ECR techx-corp."
      FAIL=1
    else
      echo "✅ Found in ECR."
    fi
  fi
done < images.txt

echo "--- AWS Inspector Vulnerability Audit ---"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"

while read -r img; do
  if [[ "$img" == "$INTERNAL_REPO"* ]]; then
    DIGEST="${img#*@}"
    RESOURCE_ID="arn:aws:ecr:${AWS_REGION}:${ACCOUNT_ID}:repository/techx-corp/${DIGEST}"
    
    echo "Querying Inspector for digest $DIGEST..."
    set +e
    out_cov=$(aws inspector2 list-coverage --filter-criteria "{
      \"resourceId\": [
        {
          \"comparison\": \"EQUALS\",
          \"value\": \"${RESOURCE_ID}\"
        }
      ],
      \"resourceType\": [
        {
          \"comparison\": \"EQUALS\",
          \"value\": \"AWS_ECR_CONTAINER_IMAGE\"
        }
      ]
    }" 2>&1)
    status_cov=$?
    
    out_find=$(aws inspector2 list-findings --filter-criteria "{
      \"ecrImageHash\": [
        {
          \"comparison\": \"EQUALS\",
          \"value\": \"${DIGEST}\"
        }
      ],
      \"findingStatus\": [
        {
          \"comparison\": \"EQUALS\",
          \"value\": \"ACTIVE\"
        }
      ]
    }" 2>&1)
    status_find=$?
    set -e
    
    if [ $status_cov -ne 0 ] || [ $status_find -ne 0 ]; then
      echo "❌ QUERY_ERROR"
      FAIL=1
    else
      # Check coverage
      covered=$(echo "$out_cov" | jq -r '.coveredResources | length')
      if [ "$covered" -eq 0 ]; then
         echo "❌ NOT_COVERED"
         FAIL=1
      else
         scan_status=$(echo "$out_cov" | jq -r '.coveredResources[0].scanStatus.statusCode // "UNKNOWN"')
         if [ "$scan_status" == "INACTIVE" ]; then
            reason=$(echo "$out_cov" | jq -r '.coveredResources[0].scanStatus.reason // "UNKNOWN"')
            echo "❌ SCAN_INACTIVE: $reason"
            FAIL=1
         elif [ "$scan_status" == "ACTIVE" ]; then
            findings=$(echo "$out_find" | jq -r '.findings')
            if [ "$findings" == "null" ] || [ "$findings" == "[]" ]; then
               echo "✅ SCANNED_NO_ACTIVE_FINDINGS"
            else
               high=$(echo "$out_find" | jq -r '[.findings[] | select(.severity == "HIGH")] | length')
               crit=$(echo "$out_find" | jq -r '[.findings[] | select(.severity == "CRITICAL")] | length')
               
               if [ "$high" -gt 0 ] || [ "$crit" -gt 0 ]; then
                  echo "❌ SCANNED_WITH_FINDINGS: HIGH=$high, CRITICAL=$crit"
                  FAIL=1
               else
                  echo "✅ SCANNED_WITH_FINDINGS (no HIGH/CRITICAL)"
               fi
            fi
         else
            echo "❌ QUERY_ERROR (Unknown scanStatus: $scan_status)"
            FAIL=1
         fi
      fi
    fi
  fi
done < images.txt

echo "--- Kubernetes Runtime Audit ---"
if ! kubectl cluster-info >/dev/null 2>&1; then
  echo "❌ RUNTIME_QUERY_ERROR (kubectl context not available)"
  if [ "$ALLOW_NO_KUBE" = "true" ]; then
    echo "⚠️ ALLOW_NO_KUBE is true, skipping runtime check..."
  else
    exit 1
  fi
else
  echo "Checking runtime pods in $NAMESPACE..."
  
  while IFS=$'\t' read -r pod_name phase spec_images spec_inits rt_images rt_inits; do
     if [ "$phase" != "Running" ] && [ "$phase" != "Pending" ]; then continue; fi
     
     echo "Pod: $pod_name"
     
     # Check Spec Images (Containers)
     for configured_img in $spec_images; do
        if [[ "$configured_img" == "$INTERNAL_REPO"* ]]; then
           echo "   Configured image reference: $configured_img"
           if ! [[ "$configured_img" == *"@sha256:"* ]]; then
              echo "   ❌ ERROR: Pod spec container is running unpinned image"
              FAIL=1
           fi
        fi
     done
     
     # Check Spec Images (Init Containers)
     for configured_img in $spec_inits; do
        if [[ "$configured_img" == "$INTERNAL_REPO"* ]]; then
           echo "   Configured init image reference: $configured_img"
           if ! [[ "$configured_img" == *"@sha256:"* ]]; then
              echo "   ❌ ERROR: Pod spec initContainer is running unpinned image"
              FAIL=1
           fi
        fi
     done

     # Check Runtime Images (Containers)
     if [ -n "$rt_images" ] && [ "$rt_images" != "<none>" ]; then
       for rt_img in $rt_images; do
          if [[ "$rt_img" == "$INTERNAL_REPO"* ]]; then
             echo "   Runtime platform imageID: $rt_img"
             if ! [[ "$rt_img" == *"@sha256:"* ]]; then
                echo "   ❌ ERROR: Pod runtime container image is not digested"
                FAIL=1
             fi
          fi
       done
     else
       echo "   ❌ ERROR: Could not get container status imageID"
       FAIL=1
     fi
     
     # Check Runtime Images (Init Containers)
     if [ -n "$spec_inits" ]; then
       if [ -n "$rt_inits" ] && [ "$rt_inits" != "<none>" ]; then
         for rt_img in $rt_inits; do
            if [[ "$rt_img" == "$INTERNAL_REPO"* ]]; then
               echo "   Runtime platform init imageID: $rt_img"
               if ! [[ "$rt_img" == *"@sha256:"* ]]; then
                  echo "   ❌ ERROR: Pod runtime initContainer image is not digested"
                  FAIL=1
               fi
            fi
         done
       else
         echo "   ❌ ERROR: Could not get initContainer status imageID"
         FAIL=1
       fi
     fi

  done < <(kubectl get pods -n "$NAMESPACE" -o custom-columns=NAME:.metadata.name,PHASE:.status.phase,SPEC_IMG:.spec.containers[*].image,SPEC_INIT:.spec.initContainers[*].image,RT_IMG:.status.containerStatuses[*].imageID,RT_INIT:.status.initContainerStatuses[*].imageID --no-headers)
fi

if [ "$FAIL" -eq 1 ]; then
  echo "Audit failed. Please fix unpinned images or errors."
  exit 1
fi

if [ "$ALLOW_NO_KUBE" = "true" ] && ! kubectl cluster-info >/dev/null 2>&1; then
  echo "T9 Evidence Collection finished with PENDING RUNTIME VERIFICATION."
else
  echo "T9 Evidence Collection Passed!"
fi
