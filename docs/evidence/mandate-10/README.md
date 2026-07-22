# Mandate 10 evidence pack

This directory contains the reviewable evidence contract for PM-127 and the
Mandate 10 secure delivery requirements. The files in this directory are
inputs or outputs of CI/GitOps verification; they are not cluster state.

## Architecture decision

Mandate 05 runtime enforcement remains on the native Kubernetes controls:

- Pod Security Admission (PSA) remains the runtime baseline mechanism.
- Native ValidatingAdmissionPolicy (VAP) remains the runtime policy mechanism
  for security context and resource requirements.
- Kyverno is restored through ArgoCD only for PM-127 supply-chain checks:
  first-party Cosign signatures and CycloneDX SBOM attestations, plus the
  reviewed external-image digest catalog.

The retired Kyverno runtime-hardening policies are intentionally not restored.
This keeps one owner for runtime admission while giving PM-127 the image
verification capability that VAP cannot provide.

Kyverno itself is pinned to chart `3.8.2` / app `v1.18.2`, which is the
supported Kyverno line for the production Kubernetes `1.35` cluster. Its
controller, migration-hook, and cleanup/test images are pinned in
`kyverno-image-allowlist.yaml`. This is a system-component inventory; it is
separate from the product-namespace external image policy.

## Requirement map

| Requirement | Repository implementation | Evidence or test |
| --- | --- | --- |
| Inventory every rendered image | `scripts/ci/render-image-inventory.py` | `test_render_image_inventory.py`; production Helm render |
| Scan first-party images before push | `.github/workflows/build-push-ecr.yml` | existing Trivy HIGH/CRITICAL gate and workflow contract tests |
| Sign first-party images | `.github/workflows/build-push-ecr.yml` | Cosign keyless sign/verify steps and release evidence upload |
| Publish CycloneDX SBOM attestations | `.github/workflows/build-push-ecr.yml` and `scripts/ci/prepare-cyclonedx-sbom.py` | `test_prepare_cyclonedx_sbom.py`, `test_workflow_sbom_contract.py` |
| Verify signature and SBOM at admission | `gitops/policies/kyverno/verify-first-party-signatures.yaml` | `test_pm127_policy_contract.py`; Kyverno CLI evaluation |
| Keep external images controlled | `docs/evidence/mandate-10/external-image-allowlist.yaml` and `gitops/policies/kyverno/allow-approved-external-image-digests.yaml` | `verify-external-image-allowlist.py`; Kyverno positive/negative fixtures |
| Deliver Kyverno declaratively | `gitops/apps/kyverno-app.yaml` and `gitops/apps/kyverno-policies-app.yaml` | sync waves 10/20, ServerSideApply, contract tests |
| Give only verifier controllers ECR read access | `infra/live/production/kyverno-ecr.tf` | Terraform format and IAM contract tests; admission and reports controllers only |
| Preserve Mandate 05 ownership | Native policy app and PSA configuration remain the source of runtime enforcement | `test_mandate05_native_retirement_contract.py` and full CI suite |

## Current rendered inventory

The exact production values render was checked offline with the same values
files used by the chart deployment:

- 31 total image references
- 19 first-party `techx-corp` image references
- 8 external image references
- 7 mutable external references remain in the preparation render
- 1 external reference (`busybox`) is already immutable
- the exact-digest catalog records the reviewed remediation target
- Kyverno admission controller: 3 replicas with PDB and topology constraints
- Kyverno reports controller: 2 replicas with PDB and topology constraints

The catalog is deliberately exact. The preparation PR does not update product
Pod templates because doing so would trigger unrelated observability/flagd
rollouts before Audit evidence exists. Audit findings are expected for the
seven mutable references; their digest changes belong in the later remediation
PR. A new external image or digest remains a reviewed code change, not an
admission-time exception or an untracked cluster edit.

## Status and limits of this evidence

The implementation is prepared in GitOps and validated offline. Both child
Applications are committed with automated reconciliation disabled, so merging
the preparation PR cannot install the webhook before its IAM role exists. A live
acceptance run is still required after the branch is merged and ArgoCD syncs:

1. Terraform plan/apply must create the Kyverno ECR read role.
2. A controller-only PR must set `kyverno` automated sync to enabled.
3. After controller health is proven, a policy-only PR must set
   `kyverno-policies` automated sync to enabled.
4. Kyverno must report both policies Ready and produce PolicyReports.
5. A real first-party digest from the signed build must show both a valid
   Cosign signature and a valid CycloneDX attestation.
6. An unapproved external tag/digest must be reported by the Audit policy.
7. Mandate 05 native VAP/PSA checks and storefront/flagd health must remain
   unchanged.
8. Only after audit evidence is reviewed should PM-127 be considered for an
   enforce-mode change. This branch keeps PM-127 in Audit.

During development, the private EKS API was reachable through the SSM tunnel,
but the active AWS identity was a read-only role that could not list ArgoCD,
Kyverno, CRDs, or ECR image metadata. Therefore no live Argo/Kyverno/ECR
claim is made by this pack, and no cluster mutation was performed.

The build workflow already supports `workflow_dispatch`. After merge, the
release owner must explicitly run it from `main` to produce the real digest,
Cosign signature, CycloneDX attestation, and uploaded evidence. A workflow-file
change alone does not trigger the build because the push path filter is scoped
to `phase3 - information/techx-corp-platform/**`.

## Evidence naming

CI release evidence is uploaded by the build workflow. The expected PM-127
artifacts are:

- rendered image inventory
- Trivy scan results
- Cosign image verification results
- CycloneDX predicate JSON
- Cosign SBOM attestation verification results
- the approved image manifest with immutable digests

Evidence must identify the source commit, workflow run/attempt, image digest,
platform, and verifier identity. A digest without those provenance fields is
not sufficient for the PM-127 acceptance record.
