# Mandate 05 Evidence Pack

This directory stores non-secret evidence for Mandate 05 runtime admission hardening.

## Working set

- `exception-register.yaml` - approved exact-label exceptions for Audit-to-Enforce review.
- PR #194 introduces or updates four Audit policies:
  `require-resource-requests`, `custom-baseline-security-context`,
  `disallow-latest-tag`, and `require-first-party-image-digest`.
- The current exception register contains 9 time-bounded exceptions that must be
  remediated or accepted before Enforce.

## Local verification flow

1. Render production with all four Argo CD values files.
2. Run `scripts/ci/verify-runtime-hardening.py` in `inventory` mode.
3. Run Kyverno CLI tests from `tests/kyverno/mandate-05/`.
4. After PR #194 is synced by Argo CD, export live PolicyReports and active Pods,
   then reconcile them against `exception-register.yaml`.
5. Collect server-side admission denial evidence only after the relevant policy
   has been promoted from Audit to Enforce.

Example live reconciliation commands:

```sh
kubectl get policyreport -A -o yaml > /tmp/mandate-05-policyreport-live.yaml
kubectl -n techx-tf3 get pods -o json > /tmp/mandate-05-pods-live.json
python3 scripts/ci/reconcile-active-policy-reports.py \
  --policyreports /tmp/mandate-05-policyreport-live.yaml \
  --pods /tmp/mandate-05-pods-live.json \
  --exceptions docs/evidence/mandate-05/exception-register.yaml \
  --output /tmp/mandate-05-reconcile-live.json
```

Expected post-sync gate: `activeFailures` and `unresolvedResults` are empty.
Historical `staleResults` from old ReplicaSets are acceptable only when they are
not tied to an active Pod UID.

## Non-goals

- No kubeconfig, tokens, or secrets are stored here.
- No imperative cluster mutation is recorded here.
- No Enforce promotion is implied by the presence of these files.
