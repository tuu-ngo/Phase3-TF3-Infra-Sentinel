# PM-127 GitOps verification runbook

This runbook verifies the PM-127 supply-chain path without applying resources
directly with `kubectl`, `helm`, or `kyverno`. The deployment source is the
`main` branch after merge; this implementation is being prepared on
`docs/mandate-10`.

## Safety boundary

Do not run `kubectl apply`, `helm upgrade`, `argocd app sync`, or
`terraform apply` from this runbook. The intended production path is:

1. Pull request review and merge to `main`.
2. Terraform plan reviewed, then the approved saved plan is applied by the
   infrastructure owner.
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
python scripts/ci/verify-external-image-allowlist.py \
  --rendered rendered.yaml \
  --allowlist docs/evidence/mandate-10/external-image-allowlist.yaml \
  --first-party-repository 197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp
kyverno test tests/kyverno/mandate-10/
```

The repository test suite also checks the workflow, Terraform IAM contract,
GitOps waves, native Mandate 05 retirement boundary, and policy structure.

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
- ECR read access for the Kyverno admission/reports controllers

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

For live admission rejection, the policy must first be intentionally promoted
to `Enforce` through a reviewed PR. That is a separate change from restoring
Kyverno and must not be inferred from an Audit PolicyReport.

## Rollback

Rollback is a Git revert through the normal PR path. The emergency owner may
temporarily disable the PM-127 Argo application only through an approved
GitOps change. Do not delete Kyverno CRDs or edit policy objects by hand,
because doing so would destroy the evidence trail and could interfere with
the native Mandate 05 controls.
