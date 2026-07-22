# PM-132 — Mandate 10 evidence, rejection demos and final report plan

**Master sequence:** `mandate-10-closure-execution-plan.md` Gate 6.

## Evidence rule

This task packages evidence; it does not pre-declare implementation complete. Every criterion starts `BLOCKED`/`IN PROGRESS` and becomes `PASS` only when the referenced run, policy state and artifact exist. Missing dependency is never rendered as `ĐẠT`.

## Demo 1 — PR security gate

Use a disposable PR only. Demonstrate the always-running `Secure delivery gate` from PM-125, its failed child/control summary, and GitHub merge lock. Use fixtures that do not contain real credentials and never merge them. The exact required context must match the Rulesets/Branches export.

Run two classes of fixture:

1. control failures: fake secret, IaC/SAST finding and platform-specific Trivy finding for AMD64/ARM64;
2. trust-boundary failure: modify aggregate to unconditional PASS or add a duplicate check name without fresh security-owner approval.

Evidence: PR URL, run URL, CODEOWNERS resolution, ruleset screenshot/JSON export, exact expected GitHub Actions source, failed aggregate/governance result and merge-lock screenshot. A green check without the governance proof does not close PM-125.

## Demo 2 — verifyImages rejects only for signature policy

The unsigned-image manifest must be compliant with every other admission policy. It must use:

- a real, resolvable ECR digest for a first-party image that lacks the required signature or has the wrong identity;
- required security context, resources, labels and namespace fields;
- a unique demo name, server-side dry-run rehearsal and actual apply final test;
- an assertion naming the exact verifyImages policy/rule rejection.

Do not use a fake digest: registry resolution can fail before admission. Do not omit resources/security context: Mandate 5 may reject it first and invalidate the demo. Capture `kubectl get clusterpolicy` showing `Enforce` and `Ready=True`. Dry-run is rehearsal only; final evidence requires actual apply non-zero and Pod absence.

### Create, prove and clean up the unsigned digest

1. Build a harmless demo image containing no production secret/data.
2. Push it to the exact ECR repository with a unique tag `mandate10-unsigned-demo-<timestamp>` using an approved demo identity.
3. Do not run `cosign sign` or the standard release workflow for this tag.
4. Resolve the real digest from ECR and form `IMAGE="$ECR_REGISTRY/techx-corp@$DIGEST"`.
5. Prove registry readability first with ECR `describe-images`/`batch-get-image`; save the resolved digest and manifest media type. A registry/auth/network failure is not unsigned-image evidence.
6. Run the exact `cosign verify` precondition below; the command must fail specifically because no valid TechX main-workflow signature exists. Also capture `cosign tree` (or equivalent attachment inventory) showing no matching signature. If verify succeeds, or failure is transport/auth/subject-not-found, abort the demo.
7. Insert the digest into a manifest compliant with every other admission policy.
8. Run `kubectl apply --dry-run=server` as rehearsal and assert the output names both `verify-first-party-signatures` and `verify-techx-main-workflow-signature`.
9. Run actual `kubectl apply`; require non-zero, the same exact policy/rule, and `kubectl get pod` returning `NotFound` rather than auth/network/RBAC failure.
10. Save build/push identity, unique tag, ECR manifest response, digest, signature-absence precondition, dry-run output, actual rejection output/exit code and Pod-absence output.
11. Retain the digest through reviewer sign-off or the approved evidence window. Delete it only after evidence is copied and another subject does not reference it; record the ECR deletion response. This is a material cleanup action and needs the approved demo owner/retention window.

```bash
ECR_REGISTRY="197826770971.dkr.ecr.ap-southeast-1.amazonaws.com"
EXPECTED_IDENTITY="https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel/.github/workflows/build-push-ecr.yml@refs/heads/main"
IMAGE="$ECR_REGISTRY/techx-corp@$DIGEST"

test "$(aws ecr batch-get-image \
  --repository-name techx-corp \
  --image-ids imageDigest="$DIGEST" \
  --query 'length(images)' --output text)" = "1" || {
  echo "FAIL: demo digest không tồn tại hoặc không đọc được từ ECR" >&2
  exit 1
}

if cosign verify \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-identity "$EXPECTED_IDENTITY" \
  "$IMAGE"; then
  echo "FAIL: demo digest đã có chữ ký hợp lệ" >&2
  exit 1
fi
```

The saved stderr must be classified by the runbook. Messages indicating credential, timeout, DNS, TLS or missing subject/manifest make the demo `INVALID`; only absence of a signature satisfying the exact issuer/identity is an acceptable unsigned precondition.

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

### Rehearsal and final apply contract

```bash
set -euo pipefail
DEMO_MANIFEST="docs/evidence/mandate-10/rejection-demo/unsigned-first-party.yaml"
EVIDENCE_DIR="docs/evidence/mandate-10/final"
mkdir -p "$EVIDENCE_DIR"

set +e
kubectl apply --dry-run=server -f "$DEMO_MANIFEST" \
  > "$EVIDENCE_DIR/unsigned-dry-run.txt" 2>&1
dry_run_rc=$?
set -e
test "$dry_run_rc" -ne 0

set +e
kubectl apply -f "$DEMO_MANIFEST" \
  > "$EVIDENCE_DIR/unsigned-actual-rejection.txt" 2>&1
apply_rc=$?
set -e
test "$apply_rc" -ne 0

for evidence in \
  "$EVIDENCE_DIR/unsigned-dry-run.txt" \
  "$EVIDENCE_DIR/unsigned-actual-rejection.txt"; do
  rg -F 'verify-first-party-signatures' "$evidence"
  rg -F 'verify-techx-main-workflow-signature' "$evidence"
done

set +e
kubectl -n techx-tf3 get pod mandate10-unsigned-demo \
  > "$EVIDENCE_DIR/unsigned-pod-absent.txt" 2>&1
get_rc=$?
set -e
test "$get_rc" -ne 0
rg -qi 'notfound|not found' "$EVIDENCE_DIR/unsigned-pod-absent.txt"
```

Nếu actual apply trả `0`, Pod tồn tại, hoặc `get` fail vì auth/RBAC/network thay vì `NotFound`, demo là `FAIL`/`INVALID`; cleanup resource qua reviewed runbook rồi điều tra trước khi thử lại.

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

ADR phải ghi rõ:

> Đây là end-to-end traceability provenance, chưa tuyên bố đạt SLSA level.

> SBOM được enforce ở release pipeline; admission giai đoạn đầu enforce signature identity và digest, chưa enforce SBOM predicate trực tiếp.

ADR cũng phải ghi trust-boundary, dual-platform CI cost, Kyverno/ECR availability dependency, pin freshness automation, 90-day retention limitation và fail-closed ambiguity trade-off.

## Acceptance matrix

| Criterion | Required evidence | Initial status |
|---|---|---|
| Governance trust boundary | CODEOWNERS/ruleset export + malicious gate-edit PR blocked | BLOCKED |
| Required PR gate | Exact GitHub Actions context + failing PR merge lock | BLOCKED |
| Scan gates | Aggregate PR run showing Gitleaks, AMD64+ARM64 Trivy, IaC and SAST | BLOCKED |
| SBOM release gate | Per-platform SBOM/index/signed provenance metadata verified | BLOCKED |
| Signature admission | Enforce/Ready; signed pass; compliant unsigned real digest actual-apply reject + Pod absent | BLOCKED |
| Pinning/freshness | Final-main dynamic Actions/Docker audit + Renovate/scheduled control | BLOCKED |
| Provenance | One-Pod `trace-result.json` PASS with source PR, promotion PR and Argo revision | BLOCKED |
| Scoped deploy | PM-131 positive/negative run and aggregate/promotion evidence | BLOCKED |
| Production health | Storefront/browse/cart/checkout/telemetry + admission latency/error evidence | BLOCKED |
| Decision/sign-off | ADR owner/reviewers/mentor approval, no expired exception | BLOCKED |

No row may be set to `PASS` merely because a plan, workflow YAML or screenshot template exists.
