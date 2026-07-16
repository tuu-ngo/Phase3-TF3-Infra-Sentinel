# Mandate 05 Evidence Pack

This directory stores non-secret evidence for Mandate 05 runtime admission hardening.

## Working set

- `exception-register.yaml` - approved exact-label exceptions for Audit-to-Enforce review.
- `../mandate-05/` - generated render, inventory, reconciliation, and admission evidence.

## Local verification flow

1. Render production with all four Argo CD values files.
2. Run `scripts/ci/verify-runtime-hardening.py` in `inventory` mode.
3. Reconcile PolicyReports against active Pods and controller UIDs.
4. Collect Kyverno CLI/server dry-run evidence for good and bad manifests.

## Non-goals

- No kubeconfig, tokens, or secrets are stored here.
- No imperative cluster mutation is recorded here.
- No Enforce promotion is implied by the presence of these files.
