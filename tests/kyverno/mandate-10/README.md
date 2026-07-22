# PM-127 Kyverno fixtures

The `kyverno-test.yaml` fixture in this directory tests only the external
exact-digest policy. It does not verify the first-party `verifyImages` rule,
because that rule must fetch private ECR signatures and attestations.

First-party verification is split deliberately:

- offline contract tests validate policy shape and failure metadata;
- `scripts/ci/get-sbom.sh` validates a real signed ECR artifact;
- `scripts/ci/verify-first-party-evidence.sh` runs the real signature/SBOM
  positive and negative matrix after release artifacts exist;
- live Kyverno Audit/Enforce checks require controller ECR access and a
  reviewed GitOps rollout.

Therefore a green `kyverno test tests/kyverno/mandate-10/` means:

```text
external allow-list fixture: passed
first-party verifyImages engine: not exercised offline
```
