#!/usr/bin/env bash
set -euo pipefail

: "${EXPECTED_REVISION:?set EXPECTED_REVISION to deploy/account-migration-gitops or main}"

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

revision_files=(
  gitops/bootstrap/application.yaml
  gitops/apps/flagd-secret-sync-app.yaml
  gitops/apps/infrastructure-app.yaml
  gitops/apps/karpenter-nodepool-app.yaml
  gitops/apps/kyverno-policies-app.yaml
  gitops/apps/techx-corp.yaml
  gitops/apps/techx-edge.yaml
)

for file in "${revision_files[@]}"; do
  grep -Eq "^[[:space:]]*targetRevision:[[:space:]]*${EXPECTED_REVISION}([[:space:]]|$)" "$file"
done

test "$(rg -l "^[[:space:]]*targetRevision:[[:space:]]*${EXPECTED_REVISION}([[:space:]]|$)" "${revision_files[@]}" | wc -l)" -eq 7
grep -Fq 'path: phase3 - information/techx-corp-chart' gitops/apps/techx-corp.yaml
grep -Fq -- '- ../deploy/values-flagd-sync.yaml' gitops/apps/techx-corp.yaml
grep -Fq -- '- ../deploy/values-prod.yaml' gitops/apps/techx-corp.yaml
grep -Fq '197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp' gitops/apps/techx-corp.yaml
grep -Fq '197826770971.dkr.ecr.ap-southeast-1.amazonaws.com' .github/workflows/build-push-ecr.yml
grep -Fq 'resource "aws_ecr_repository" "techx_corp"' infra/live/production/ecr.tf
grep -Fq 'prevent_destroy = true' infra/live/production/ecr.tf
grep -Fq 'repository = aws_ecr_repository.techx_corp.name' infra/live/production/ecr.tf

if rg -n '012619468490' .github infra gitops 'phase3 - information/deploy/values-prod.yaml'; then
  echo 'old AWS account found in an active production path' >&2
  exit 1
fi

echo "cutover repository validation passed for ${EXPECTED_REVISION}"
