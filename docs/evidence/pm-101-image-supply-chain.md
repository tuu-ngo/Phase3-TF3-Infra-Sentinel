# PM-101 evidence — Trivy scan gate and keyless Cosign signing

**Task:** `[MANDATE 5] Scan gate (Trivy) + ký xác thực image (Cosign) trước khi vào cluster`

**Backlog:** item #8 / PM-101, extending PM-95 digest pinning and ECR immutability

**Branch:** `feat/pm-101-trivy-cosign-gate`

**Date:** 2026-07-16

**Status:** implementation ready for PR; remote CI, signature, and live-digest
evidence remain pending until the workflow is merged and run on `main`

## 1. Scope and isolation from PM-92

This branch is created from the current `origin/main` and contains only PM-101
CI, supply-chain documentation, and evidence changes:

- `.github/workflows/build-push-ecr.yml`
- `.github/workflows/scan-external-images.yml`
- `docs/adr/0008-pm-101-image-supply-chain-gate.md`
- `docs/security/image-supply-chain-controls.md`
- `docs/evidence/pm-101-image-supply-chain.md`

It deliberately does **not** contain PM-92 changes to
`phase3 - information/techx-corp-chart/values.yaml` or application Dockerfiles.
Merging this branch therefore does not change Kubernetes pod templates, runtime
UIDs, security contexts, image digests, replicas, public storefront routing,
private operations access, or flagd/fault-injection behavior.

## 2. Before PM-101

The production baseline before this branch had these properties:

| Area | Before |
| --- | --- |
| Build order | Buildx pushed the selected multi-architecture images to ECR first. |
| Vulnerability gate | Trivy scanned the ECR image after push with `HIGH,CRITICAL`; a failed scan stopped the job but the candidate already existed in the registry. |
| Scan evidence | No per-service JSON artifact was uploaded by the release workflow. |
| Provenance | No Cosign signing or verification step existed. |
| External images | No dedicated scheduled, non-blocking Trivy evidence workflow existed on `main`. |
| ECR baseline | `imageTagMutability=IMMUTABLE` and `scanOnPush=true`; live audit on 2026-07-16 found zero Cosign signature tags/artifacts. |
| Existing evidence | `docs/scan-evidence.txt` covered one ECR digest, not every first-party image running in the cluster. |

This meant the pipeline could detect a vulnerable image, but could not prevent
that candidate from reaching ECR and could not prove that a deployed digest was
built and signed by the TF3 GitHub Actions identity.

## 3. What PM-101 changes

### First-party images

The workflow now performs this sequence for every selected build target:

```text
detect changed services
  -> build a local linux/amd64 candidate
  -> write a per-service Trivy JSON report
  -> fail on any HIGH or CRITICAL vulnerability
  -> upload Trivy evidence even when the gate fails
  -> build and push the multi-architecture ECR image only after a clean gate
  -> resolve the immutable ECR manifest-list digest
  -> keyless Cosign sign using GitHub Actions OIDC
  -> Cosign verify the pushed digest and certificate identity
  -> upload the digest/report/run mapping and raw verification output
```

The agreed threshold is zero `HIGH` and zero `CRITICAL`, including unfixed
findings. No static Cosign private key or password is stored in the repository
or GitHub Secrets.

The historical ticket says 18 app services. The current repository has 20
build targets in `ALL_SERVICES`; PM-101 gates and signs the superset so an
auxiliary target cannot bypass the control. The final Jira evidence must label
the agreed 18 app services and any additional auxiliary targets explicitly.

### External images

PostgreSQL, Grafana, Jaeger, OpenSearch, Prometheus, OTel Collector, Valkey, and
Flagd are upstream artifacts. TF3 must not sign them as if TF3 built them. A
weekly/manual workflow scans their pinned digests, uploads JSON reports, and
does not use `--exit-code 1`; missing TF3 signatures therefore do not block the
first-party application release.

## 4. Impact assessment

### Positive impact

- Vulnerable first-party candidates are blocked before the normal ECR push.
- Every pushed first-party digest receives a short-lived, auditable GitHub OIDC
  signature rather than a long-lived private signing key.
- Release evidence maps the Git commit and Actions run to the ECR digest,
  Trivy report, certificate identity, and raw Cosign verification output.
- External-image ownership and signature exceptions become explicit and
  reviewable instead of silently bypassing the first-party control.

### Operational trade-offs and risks

- CI builds the amd64 candidate before the later multi-architecture push, so
  release duration and GitHub Actions usage increase.
- The zero HIGH/CRITICAL threshold can block urgent releases until the base
  image or dependency is patched or Security records a reviewed exception.
- The pre-push gate scans the EKS runtime architecture (`linux/amd64`). The
  pushed manifest also contains `linux/arm64`; arm64 is not an EKS runtime in
  this environment and is not independently scanned by this implementation.
- The scheduled external scan consumes GitHub Actions minutes but creates no
  new cluster service and no fixed infrastructure cost.
- Merging the branch alone creates no signatures. Signatures and proof exist
  only after a successful workflow run on `main`.

Overall assessment: the security and auditability gain is positive. The main
negative effect is stricter, longer CI; that is intentional because a release
with an unreviewed HIGH/CRITICAL finding must stop.

## 5. Safe rollout flow

1. Review this branch and confirm its diff contains no PM-92 runtime files.
2. Merge the PM-101 PR into `main`.
3. Run `Build & Push TechX Corp images to ECR` manually in full mode on `main`.
4. Remediate every HIGH/CRITICAL finding until the full run is green.
5. Download `trivy-app-images-<run-id>` and
   `signed-release-evidence-<run-id>`.
6. Confirm every required service has a Trivy JSON report, a digest entry, and
   a successful raw `cosign verify` report.
7. Record the exact signed digest and Actions run in `docs/release-notes-v1.md`.
8. Promote only those signed digests through a separate GitOps PR.
9. Verify the live pod image digests match the evidence table.
10. Run `Periodic Trivy review for external images` once manually and retain
    its first artifact before relying on the weekly schedule.

Steps 7-9 are deliberately separate from this CI-only branch so merging PM-101
cannot cause an unreviewed workload rollout.

## 6. Evidence state

| Evidence | Before | Branch/static result | Required after merge |
| --- | --- | --- | --- |
| PM-101 isolated from PM-92 | Mixed integration branch | Pass: only CI/docs/evidence files | Keep the PR diff isolated. |
| Pre-push HIGH/CRITICAL gate | No | Implemented | One green full run plus a controlled failing-gate demonstration or failed run artifact. |
| Per-service Trivy JSON | No release artifact | Implemented | Artifact must cover every required service. |
| Keyless Cosign signing | No | Implemented | ECR digest signatures must exist. |
| Immediate Cosign verification | No | Implemented | Raw verify report for every signed digest. |
| Digest/run/report mapping | No | Implemented as `signed-images.jsonl` | Attach artifact and summary table to Jira. |
| External-image exception list | Informal | Documented | Run the external workflow and retain its artifact. |
| Live cluster runs signed digests | No proof | Out of this branch's mutation scope | Promote signed digests separately and compare live state. |

### Branch validation record — 2026-07-16

- Branch base: `origin/main@f817e17`.
- PM-101 history is split into five reviewable phases: first-party gate/sign
  (`b71891b`), safe Buildx targets (`6529b89`), signature verification/evidence
  (`61965eb`), external exceptions plus ADR (`67a143c`), and this final
  before/after evidence phase.
- `actionlint` passed for both changed workflows.
- `git diff --check` passed.
- The final branch diff is limited to the five PM-101 CI/ADR/docs/evidence files
  listed in section 1; no PM-92 chart or Dockerfile is present.
- No workflow was dispatched, ECR artifact mutated, GitOps value changed, or
  Kubernetes resource applied while preparing this branch.

## 7. Commands used for final verification

Verify branch isolation before merge:

```bash
git diff --name-status origin/main...HEAD
git diff --check origin/main...HEAD
```

Verify a first-party signature independently:

```bash
cosign verify \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-identity https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel/.github/workflows/build-push-ecr.yml@refs/heads/main \
  197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp@sha256:<digest>
```

Compare the first-party digests actually running in the namespace:

```bash
kubectl get pods -n techx-tf3 -o json \
  | jq -r '.items[].spec.containers[].image' \
  | rg '197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp@sha256:' \
  | sort -u
```

## 8. Rollback

If the new CI control causes an unintended release outage, revert the PM-101
merge commit on `main`. This restores the previous workflow and removes the
scheduled external review. Rollback does not restart pods, change deployed
digests, alter ECR immutability, expose private operations endpoints, or disable
flagd. A Security-approved temporary exception must be documented separately;
do not silently weaken `TRIVY_SEVERITIES` or remove Cosign verification.

## 9. Definition of Done

- [x] Blocking Trivy step is before the normal ECR push in branch code.
- [x] Threshold is explicitly zero HIGH/CRITICAL.
- [x] Keyless Cosign signing and immediate verification are implemented.
- [x] External-image exception and non-blocking periodic scan are documented.
- [x] PM-101 changes are isolated from PM-92 runtime hardening.
- [ ] Full workflow run on `main` is green.
- [ ] Trivy artifact covers every agreed first-party service.
- [ ] Every pushed first-party digest has a successful Cosign verification.
- [ ] Jira/release evidence maps each running digest to its scan and signature.
- [ ] External-image workflow has produced its first retained artifact.

PM-101 must remain open until every unchecked runtime/evidence item above is
complete. A green branch diff is implementation evidence, not production proof.
