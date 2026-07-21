# PM-132 — Mandate 10 evidence, rejection demos and final report plan

## Evidence rule

This task packages evidence; it does not pre-declare implementation complete. Every criterion starts `BLOCKED`/`IN PROGRESS` and becomes `PASS` only when the referenced run, policy state and artifact exist. Missing dependency is never rendered as `ĐẠT`.

## Demo 1 — PR security gate

Use a disposable PR only. Demonstrate the always-running `Secure delivery gate` from PM-125, its failed child/control summary, and GitHub merge lock. Use fixtures that do not contain real credentials and never merge them. The exact required context must match the Rulesets/Branches export.

Evidence: PR URL, run URL, ruleset screenshot/export, failed aggregate result and merge-lock screenshot.

## Demo 2 — verifyImages rejects only for signature policy

The unsigned-image manifest must be compliant with every other admission policy. It must use:

- a real, resolvable ECR digest for a first-party image that lacks the required signature or has the wrong identity;
- required security context, resources, labels and namespace fields;
- a unique demo name and server-side dry-run;
- an assertion naming the exact verifyImages policy/rule rejection.

Do not use a fake digest: registry resolution can fail before admission. Do not omit resources/security context: Mandate 5 may reject it first and invalidate the demo. Capture `kubectl apply --dry-run=server` output plus `kubectl get clusterpolicy` showing `Enforce` and `Ready=True`.

### Create, prove and clean up the unsigned digest

1. Build a harmless demo image containing no production secret/data.
2. Push it to the exact ECR repository with a unique tag `mandate10-unsigned-demo-<timestamp>` using an approved demo identity.
3. Do not run `cosign sign` or the standard release workflow for this tag.
4. Resolve the real digest from ECR and form `IMAGE="$ECR_REGISTRY/techx-corp@$DIGEST"`.
5. Run the exact `cosign verify` precondition below; the command must fail because no valid TechX main-workflow signature exists. If it succeeds, abort the demo.
6. Insert the digest into a manifest compliant with every other admission policy.
7. Run `kubectl apply --dry-run=server` and assert the output names both `verify-first-party-signatures` and `verify-techx-main-workflow-signature`.
8. Save build/push identity, tag, digest, precondition output and admission rejection output.
9. Delete the demo tag/digest only after evidence is copied and another subject does not reference it. Record the ECR deletion response. This is a material cleanup action and needs the approved demo owner/retention window.

```bash
ECR_REGISTRY="197826770971.dkr.ecr.ap-southeast-1.amazonaws.com"
EXPECTED_IDENTITY="https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel/.github/workflows/build-push-ecr.yml@refs/heads/main"
IMAGE="$ECR_REGISTRY/techx-corp@$DIGEST"

if cosign verify \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-identity "$EXPECTED_IDENTITY" \
  "$IMAGE"; then
  echo "FAIL: demo digest đã có chữ ký hợp lệ" >&2
  exit 1
fi
```

The demo container must include at least:

```yaml
resources:
  requests:
    cpu: 10m
    memory: 16Mi
  limits:
    cpu: 50m
    memory: 32Mi
securityContext:
  runAsNonRoot: true
  allowPrivilegeEscalation: false
  capabilities:
    drop: ["ALL"]
  seccompProfile:
    type: RuntimeDefault
```

Do not treat a generic registry, resource, baseline-security or image-reference rejection as proof of `verifyImages`.

## Demo 3 — provenance

Use the PM-129 CLI contract, selecting a real running pod/container and final SBOM predicate agreed by PM-127:

```bash
./scripts/ci/trace-provenance.sh \
  --namespace techx-tf3 \
  --pod <pod> \
  --container <container> \
  --sbom-type cyclonedx
```

Before PM-127 is complete, rehearsal is explicitly non-final:

```bash
./scripts/ci/trace-provenance.sh \
  --namespace techx-tf3 --pod <pod> --container <container> \
  --allow-pending-sbom
```

Only `REHEARSAL_BLOCKED_BY_PM_127` is valid in that state. Final evidence requires `overallResult == "PASS"`, `sbomVerified == true`, and no `--allow-pending-sbom`.

## Preflight

Confirm `aws`, `gh`, `kubectl`, `jq`, `cosign`, `docker`; GitHub auth; exact AWS profile/account; ECR login; Kubernetes pod-read RBAC; and a real image deployed by the standard release workflow. The runbook must fail closed if any preflight item is unavailable.

```bash
export AWS_PROFILE=techx-new
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
[ "$ACCOUNT" = "197826770971" ] || {
  echo "FAIL: wrong AWS account: $ACCOUNT" >&2
  exit 1
}
```

## Report and ADR

Create the final report and ADR only after evidence exists. Map all six Mandate 10 requirements to exact workflow run IDs, policy state, artifact locations/retention and demo URLs. The ADR records accepted trade-offs, exceptions, rollback through GitOps (not imperative policy mutation), decision owner/reviewers/mentor sign-off.

## Acceptance matrix

| Criterion | Required evidence | Initial status |
|---|---|---|
| Required PR gate | Admin ruleset export + failing PR | BLOCKED |
| Scan gates | Aggregate PR run showing Gitleaks/Trivy/IaC/SAST | BLOCKED |
| Signature admission | Compliant unsigned real digest rejected by verifyImages | BLOCKED |
| Pinning | Final-main dynamic audit output | BLOCKED |
| Provenance | `trace-result.json` PASS + SBOM | BLOCKED |
| Scoped deploy | PM-131 run/aggregate manifest | BLOCKED |

No row may be set to `PASS` merely because a plan, workflow YAML or screenshot template exists.
