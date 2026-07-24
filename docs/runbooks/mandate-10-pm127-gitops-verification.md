# PM-127 GitOps verification runbook

This runbook verifies the PM-127 supply-chain path without applying resources
directly with `kubectl`, `helm`, or `kyverno`. The deployment source is the
`main` branch after merge. The preparation implementation was merged by PR
#349; every rollout step below remains separately reviewed.

## Safety boundary

Do not run `kubectl apply`, `helm upgrade`, `argocd app sync`, or
`terraform apply` from this runbook. The intended production path is:

1. Pull request review and merge to `main`.
2. Terraform plan reviewed, then the approved saved plan is applied by the
   infrastructure owner. Use the fixed `pm127-kyverno-ecr` scope while the
   full production plan contains unrelated changes.
3. A reviewed controller-only PR enables automated reconciliation for the
   `kyverno` child Application.
4. After the controller is healthy, a policy-only PR enables automated
   reconciliation for `kyverno-policies`.
5. Live checks below are read-only, except for the explicitly labelled mentor
   rejection demo, which must be approved and run in a controlled namespace.

## Pre-merge checks

Run from the repository root:

```sh
python -m pytest -q scripts/ci
helm lint "phase3 - information/techx-corp-chart" \
  -f "phase3 - information/techx-corp-chart/values.yaml" \
  -f "phase3 - information/deploy/values-flagd-sync.yaml" \
  -f "phase3 - information/deploy/values-prod.yaml" \
  -f "phase3 - information/deploy/values-aio-llm.yaml"
python scripts/ci/render-image-inventory.py \
  --rendered rendered.yaml \
  --first-party-repository 197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp \
  --output image-inventory.json
kyverno test tests/kyverno/mandate-10/

# Read one signed, non-empty CycloneDX SBOM from an immutable first-party ref.
# For a multi-platform index, --platform is mandatory.
scripts/ci/get-sbom.sh \
  197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp@sha256:<index> \
  --platform linux/amd64 \
  --metadata
```

The repository test suite also checks the workflow, Terraform IAM contract,
GitOps waves, native Mandate 05 retirement boundary, and policy structure.
The Kyverno fixture here is intentionally external-only; a green result does
not claim that private-ECR first-party `verifyImages` verification ran offline.
Use the live first-party evidence matrix below after a trusted release exists.
The preparation render intentionally still contains seven mutable external
references. Do not pin them in this PR: first collect Audit findings, then run
`verify-external-image-allowlist.py` as a required gate in the remediation PR.
The scheduled external Trivy workflow reads the same catalog file used by the
Kyverno policy; it must not carry a second hardcoded image list.

## Required identity and connectivity

Use the production account profile before any AWS or Kubernetes command:

```sh
export AWS_PROFILE=techx-new
export AWS_REGION=ap-southeast-1
```

With the SSM port-forward already running on local port 8443, configure the
private EKS endpoint as described in `AGENTS.md`. First verify identity and
API reachability:

```sh
aws sts get-caller-identity
kubectl --raw=/version
kubectl auth can-i get applications.argoproj.io -n argocd
kubectl auth can-i list clusterpolicies.kyverno.io
aws ecr describe-repositories --repository-names techx-corp
```

Stop if the account is not `197826770971` or if the identity lacks the
read-only checks above. A tunnel can be healthy while the AWS role is still
unable to inspect the cluster or ECR.

## Post-merge GitOps observation

### Apply only the PM-127 IRSA prerequisite

The automatic plan for the PR #349 merge showed the two expected Kyverno IAM
resources together with unrelated production changes, including a bastion
replacement and datastore/audit updates. Do not apply that full plan as part
of PM-127.

After the scoped-rollout workflow change is merged, dispatch **Terraform Apply
(production)** from `main` with:

```text
action: apply
scope: pm127-kyverno-ecr
```

The plan job uses a closed, repository-owned target list:

```text
aws_iam_role.kyverno_ecr
aws_iam_role_policy.kyverno_ecr_read
```

Before approving the `production` environment, inspect the plan log. It must
show only those two resources and this summary:

```text
Plan: 2 to add, 0 to change, 0 to destroy.
```

Reject the environment approval if any bastion, EKS, datastore, edge, audit,
or other resource appears. The apply job verifies the downloaded plan hash,
applies that exact `tfplan`, then calls `iam:GetRole` and `iam:GetRolePolicy` to
prove both live IAM objects exist. Keep `scope: full` for normal, separately
reviewed infrastructure releases; it is not the PM-127 rollout path.

After the infrastructure owner applies the reviewed Terraform plan, merge the
controller enablement PR and observe ArgoCD without forcing a sync:

```sh
kubectl -n argocd get application kyverno kyverno-policies -o wide
kubectl -n kyverno get pods,sa
kubectl get clusterpolicies.kyverno.io
kubectl get crd clusterpolicies.kyverno.io
```

Expected ordering and state:

- `kyverno-app.yaml` sync wave 10 creates the controller and CRDs.
- `kyverno-policies-app.yaml` sync wave 20 creates the two PM-127 policies.
- admission and reports controller service accounts have the dedicated ECR
  read-role annotation because admission verifies new requests and reports
  performs background scans.
- background and cleanup service accounts do not receive that annotation.
- admission has three replicas and reports has two replicas, each with a PDB
  and topology constraints.
- both policies are `Ready` and remain `Audit`.

Terraform and Argo are separate reconcilers. Argo sync waves cannot prove that
the Terraform IAM role already exists. The preparation branch therefore keeps
automated reconciliation disabled for both child Applications. Do not manually
sync them. Enable the controller through a PR only after IAM is applied, and
enable Audit policies through a later PR only after controller health is proven.

If Argo reports `ComparisonError`, inspect chart dependencies and the exact
Git revision before touching the cluster. Do not bypass GitOps with a manual
apply.

## Live policy checks

Read the policy reports and verify that every first-party image has a useful
result rather than an `ImageVerify` configuration error:

```sh
kubectl get policyreports -A
kubectl get clusterpolicyreports -o yaml
kubectl describe clusterpolicy verify-first-party-signatures
kubectl describe clusterpolicy allow-approved-external-image-digests
```

The first-party policy needs all of the following to succeed:

- immutable ECR digest
- Cosign keyless signature
- GitHub Actions workflow identity for the `main` build workflow
- Fulcio issuer `https://token.actions.githubusercontent.com`
- Rekor inclusion at `https://rekor.sigstore.dev`
- CycloneDX predicate type `https://cyclonedx.org/bom`
- non-empty CycloneDX components with TechX index/child/platform/source metadata
- ECR read access for the Kyverno admission/reports controllers

For a multi-platform release, the Kubernetes desired state pins the index digest
while the runtime image ID may be a child digest. The workflow signs the index,
attests each platform SBOM to its child, and publishes a signed index-to-platform
mapping. Retrieval resolves the index before verifying the exact child SBOM.

The ECR role is attached to the admission and reports controllers. The
background controller is intentionally excluded because these PM-127 policies
do not use generate/mutate-existing processing; the reports controller owns
background scans.

The external policy needs the exact digest to be present in
`docs/evidence/mandate-10/external-image-allowlist.yaml`. A tag, a different
digest, or a new external repository should be visible as an Audit violation.

## Mentor rejection demonstration

Run this only after the reviewer approves a controlled test and the team has
confirmed that PM-127 is still in Audit. Use the repository fixtures as the
source of truth:

```sh
kyverno apply gitops/policies/kyverno/allow-approved-external-image-digests.yaml \
  --resource tests/kyverno/mandate-10/resources/valid-pod.yaml \
  --detailed-results
kyverno apply gitops/policies/kyverno/allow-approved-external-image-digests.yaml \
  --resource tests/kyverno/mandate-10/resources/bad-pod.yaml \
  --detailed-results
```

Offline expected result:

- valid fixture: pass
- bad fixture: the `require-approved-external-image-digest` rule fails

These two offline commands do not exercise the private-ECR first-party policy.
That policy requires the live Kyverno controllers to have ECR read access and
is verified with real signed artifacts by the matrix below.

After a real first-party release has produced immutable evidence, execute the
first-party matrix with the release owner’s fixture references:

```sh
scripts/ci/verify-first-party-evidence.sh \
  --valid-image '<signed-index-or-child-digest>' \
  --unsigned-image '<unsigned-digest>' \
  --wrong-issuer-image '<digest-signed-by-wrong-issuer>' \
  --wrong-identity-image '<digest-signed-by-wrong-workflow>' \
  --missing-sbom-image '<signed-digest-without-cyclonedx>' \
  --wrong-predicate-image '<signed-digest-with-wrong-predicate>' \
  --tagged-image '197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp:<tag>'
```

The command is intentionally not part of the pre-merge suite: those fixtures
must be real ECR artifacts and must never be laptop-signed. It fails closed when
any expected rejection unexpectedly succeeds.

For live admission rejection, the policy must first be intentionally promoted
to `Enforce` through a reviewed PR. That is a separate change from restoring
Kyverno and must not be inferred from an Audit PolicyReport.

## Rollback

Rollback is a Git revert through the normal PR path. The emergency owner may
temporarily disable the PM-127 Argo application only through an approved
GitOps change. Do not delete Kyverno CRDs or edit policy objects by hand,
because doing so would destroy the evidence trail and could interfere with
the native Mandate 05 controls.
