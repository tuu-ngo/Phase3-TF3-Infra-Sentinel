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

Confirm `aws`, `gh`, `kubectl`, `jq`, `cosign`, `docker`; GitHub auth; AWS identity; ECR login; Kubernetes pod-read RBAC; and a real image deployed by the standard release workflow. The runbook must fail closed if any preflight item is unavailable.

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
