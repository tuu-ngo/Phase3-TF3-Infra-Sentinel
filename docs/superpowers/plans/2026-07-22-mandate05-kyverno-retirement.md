# Mandate 05 Kyverno Retirement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retire the remaining Mandate 05 Kyverno policies and controller through GitOps after proving that native VAP and PSA enforcement covers the approved production scope, then restore a clean Argo CD state without customer impact.

**Architecture:** Make repository contracts fail before deleting Kyverno declarations, then remove the policy Application and stale Kyverno tests, correct the ADR/evidence boundary for the future Mandate 10 webhook, and enable Server-Side Apply for self-managed Argo CD. Production reconciliation is a separately approved operational stage: Argo prunes the wave-20 policy Application before the already-removed wave-10 controller Application, with live admission, readiness, and SLO gates before and after.

**Tech Stack:** Kubernetes 1.35, Argo CD 3.4.5, ValidatingAdmissionPolicy/CEL, Pod Security Admission, Helm, Python 3, pytest, PyYAML, kubectl, GitHub Actions.

## Global Constraints

- Start implementation from the newest `origin/main` in an isolated worktree; never modify the user's dirty checkout.
- Never push directly to `main`.
- Production inspection is read-only until the user separately approves the monitored bootstrap reconciliation.
- Never run `kubectl apply`, patch, delete, edit, scale, Argo sync, or Terraform apply during repository implementation.
- Server-side dry-run is allowed only after AWS account `197826770971`, expected identity, tunnel, and context are verified.
- `observability-system` must remain PSA warn/audit only; do not add `pod-security.kubernetes.io/enforce` there.
- `kube-system` must remain excluded from both Mandate 05 native VAP bindings.
- Do not weaken either VAP binding from `Deny`.
- Do not touch `flagd`, OpenFeature hooks, `/flagservice`, Envoy fault injection, secrets, tokens, kubeconfigs, or credential files.
- Do not resolve `ExternalSecret/postgres-connection` drift in this change.
- Mandate 10 is not implemented by this plan; document its future webhook-plus-VAP boundary without building the webhook.
- Use branch -> PR -> merge -> Argo reconciliation; never manually delete Kyverno resources.

---

### Task 1: Add a failing native-admission retirement contract

**Files:**
- Create: `scripts/ci/test_mandate05_native_retirement_contract.py`
- Test: `scripts/ci/test_mandate05_native_retirement_contract.py`

**Interfaces:**
- Consumes: native policy YAML, namespace YAML, Argo child Applications, and `argocd-self` declaration.
- Produces: a CI contract that prevents Kyverno declarations from returning, prevents native enforcement scope from weakening, preserves the observability exception, and requires Server-Side Apply for Argo self-management.

- [ ] **Step 1: Create the contract test**

Create `scripts/ci/test_mandate05_native_retirement_contract.py` with this complete content:

```python
from pathlib import Path

import yaml


REPO = Path(__file__).resolve().parents[2]


def load_documents(relative_path: str) -> list[dict]:
    with (REPO / relative_path).open(encoding="utf-8") as stream:
        return [document for document in yaml.safe_load_all(stream) if document]


def named_documents(relative_path: str) -> dict[str, dict]:
    return {
        document["metadata"]["name"]: document
        for document in load_documents(relative_path)
    }


def test_native_vap_bindings_remain_deny_and_exclude_only_kube_system():
    documents = named_documents("gitops/policies/native/mandate-05-runtime-policy.yaml")
    expected = {
        "mandate05-native-resource-requirements-techx-tf3",
        "mandate05-native-image-reference-techx-tf3",
    }

    for name in expected:
        binding = documents[name]
        assert binding["kind"] == "ValidatingAdmissionPolicyBinding"
        assert binding["spec"]["validationActions"] == ["Deny"]
        expressions = binding["spec"]["matchResources"]["namespaceSelector"][
            "matchExpressions"
        ]
        assert expressions == [
            {
                "key": "kubernetes.io/metadata.name",
                "operator": "NotIn",
                "values": ["kube-system"],
            }
        ]


def test_psa_enforcement_and_observability_exception_are_explicit():
    techx = load_documents("gitops/infrastructure/namespace-techx-tf3.yaml")[0]
    techx_labels = techx["metadata"]["labels"]
    assert techx_labels["pod-security.kubernetes.io/enforce"] == "restricted"
    assert techx_labels["pod-security.kubernetes.io/enforce-version"] == "v1.35"

    observability = load_documents(
        "gitops/infrastructure/namespace-observability-system.yaml"
    )[0]
    observability_labels = observability["metadata"]["labels"]
    assert "pod-security.kubernetes.io/enforce" not in observability_labels
    assert observability_labels["pod-security.kubernetes.io/warn"] == "baseline"
    assert observability_labels["pod-security.kubernetes.io/audit"] == "baseline"


def test_kyverno_is_absent_from_gitops_desired_state():
    assert not (REPO / "gitops/apps/kyverno-app.yaml").exists()
    assert not (REPO / "gitops/apps/kyverno-policies-app.yaml").exists()
    assert not (REPO / "gitops/policies/kyverno").exists()


def test_argocd_self_uses_server_side_apply():
    application = load_documents("gitops/apps/argocd-self-app.yaml")[0]
    sync_options = application["spec"]["syncPolicy"]["syncOptions"]
    assert "ServerSideApply=true" in sync_options
```

- [ ] **Step 2: Install the pinned test dependencies**

Run:

```bash
python3 -m pip install -r scripts/ci/requirements-runtime-hardening.txt pytest==8.4.1
```

Expected: installation succeeds with `PyYAML==6.0.2` and `pytest==8.4.1` available.

- [ ] **Step 3: Run the contract and prove it fails for only the intended gaps**

Run:

```bash
python3 -m pytest scripts/ci/test_mandate05_native_retirement_contract.py -q
```

Expected: VAP and PSA tests pass; the Kyverno-absence test fails because `kyverno-policies-app.yaml` and `gitops/policies/kyverno/` still exist; the Argo self-management test fails because `syncOptions` is not present yet.

- [ ] **Step 4: Commit the failing contract**

```bash
git add scripts/ci/test_mandate05_native_retirement_contract.py
git commit -m "test: define native admission retirement contract"
```

---

### Task 2: Remove the remaining Mandate 05 Kyverno desired state

**Files:**
- Delete: `gitops/apps/kyverno-policies-app.yaml`
- Delete: `gitops/policies/kyverno/baseline-security-context.yaml`
- Delete: `gitops/policies/kyverno/disallow-latest-tag.yaml`
- Delete: `gitops/policies/kyverno/require-first-party-image-digest.yaml`
- Delete: `gitops/policies/kyverno/require-resource-requests.yaml`
- Delete: `tests/kyverno/mandate-05/kyverno-test.yaml`
- Delete: all fixtures under `tests/kyverno/mandate-05/resources/`
- Test: `scripts/ci/test_mandate05_native_retirement_contract.py`

**Interfaces:**
- Consumes: the native contract added in Task 1 and the already-merged removal of `gitops/apps/kyverno-app.yaml`.
- Produces: desired state with no Kyverno controller or ClusterPolicy Application, while leaving VAP/PSA declarations unchanged.

- [ ] **Step 1: Delete only the obsolete Kyverno declarations and tests**

Use `apply_patch` to delete the exact files listed above. Do not delete native rejection fixtures under `docs/evidence/mandate-05/native-rejection-demo/`.

- [ ] **Step 2: Verify no active GitOps or test declaration references Kyverno**

Run:

```bash
test ! -e gitops/apps/kyverno-app.yaml
test ! -e gitops/apps/kyverno-policies-app.yaml
test ! -e gitops/policies/kyverno
test ! -e tests/kyverno/mandate-05
rg -n 'gitops/policies/kyverno|tests/kyverno/mandate-05' gitops scripts tests .github || true
```

Expected: all four `test` commands succeed and `rg` returns no active reference.

- [ ] **Step 3: Re-run the contract**

Run:

```bash
python3 -m pytest scripts/ci/test_mandate05_native_retirement_contract.py -q
```

Expected: only `test_argocd_self_uses_server_side_apply` still fails.

- [ ] **Step 4: Commit the desired-state removal**

```bash
git add -A gitops/apps/kyverno-policies-app.yaml gitops/policies/kyverno tests/kyverno/mandate-05
git commit -m "chore: retire Mandate 05 Kyverno policies"
```

---

### Task 3: Make Argo self-management safe for large CRDs

**Files:**
- Modify: `gitops/apps/argocd-self-app.yaml`
- Test: `scripts/ci/test_mandate05_native_retirement_contract.py`

**Interfaces:**
- Consumes: Argo CD Application sync options.
- Produces: Argo CD self-sync using Server-Side Apply so the ApplicationSet CRD does not exceed the client-side last-applied annotation limit.

- [ ] **Step 1: Add the minimal sync option**

Under `spec.syncPolicy`, keep the existing automated policy and add:

```yaml
    syncOptions:
      - ServerSideApply=true
```

The resulting block must be exactly:

```yaml
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - ServerSideApply=true
```

- [ ] **Step 2: Run the contract and Argo manifest checks**

Run:

```bash
python3 -m pytest scripts/ci/test_mandate05_native_retirement_contract.py -q
kubectl apply --dry-run=client -f gitops/apps/argocd-self-app.yaml
kubectl kustomize gitops/bootstrap/argocd >/tmp/argocd-self-rendered.yaml
test -s /tmp/argocd-self-rendered.yaml
```

Expected: all contract tests pass, client dry-run succeeds, and the Argo bootstrap render is non-empty.

- [ ] **Step 3: Commit the Argo fix**

```bash
git add gitops/apps/argocd-self-app.yaml
git commit -m "fix: use server-side apply for Argo self-management"
```

---

### Task 4: Correct the Mandate 05 and Mandate 10 decision record

**Files:**
- Modify: `docs/adr/0010-mandate-05-runtime-hardening.md`
- Modify: `docs/evidence/mandate-05/native-migration-20260721.md`
- Create: `docs/runbooks/mandate-05-kyverno-retirement.md`

**Interfaces:**
- Consumes: the approved design and current live evidence.
- Produces: one consistent decision boundary and an operator-ready, approval-gated retirement runbook.

- [ ] **Step 1: Correct ADR 0010 without rewriting historical evidence**

In the `Update 2026-07-22` section, replace claims that Kyverno must remain for an already-active Mandate 10 control with this exact decision paragraph:

```markdown
**Mandate 10 boundary:** Mandate 10 admission verification is not implemented
at this retirement point. CI signs and verifies first-party images, but no
live `verifyImages` admission policy currently depends on Kyverno. Mandate 10
will use a dedicated signature/provenance validating webhook together with VAP;
that future webhook is a separate design, rollout, and acceptance gate. Retiring
Kyverno here removes no active signature-verification admission control.
```

Keep the historical statements that explain what was believed at the time, but mark them superseded by this dated decision rather than silently deleting the history.

- [ ] **Step 2: Update the native migration evidence status**

Add a dated retirement addendum containing exactly these outcome fields, leaving values as evidence states rather than unsupported claims:

```markdown
## Retirement addendum — 2026-07-22

- Native VAP enforcement: `LIVE-VERIFIED`, both bindings `Deny`.
- PSA Restricted enforcement: `LIVE-VERIFIED` on approved application/platform namespaces.
- `observability-system`: intentional `warn/audit` exception; no Restricted enforcement.
- `kube-system`: intentional VAP/PSA system exception.
- Mandate 05 Kyverno policies: removal proposed by the retirement PR; not complete until Argo prune and post-reconcile gates pass.
- Mandate 10: not implemented; future design is a dedicated signature/provenance webhook plus VAP.
```

- [ ] **Step 3: Create the operational runbook**

Create `docs/runbooks/mandate-05-kyverno-retirement.md` with these sections and commands:

```markdown
# Mandate 05 Kyverno Retirement Runbook

## Safety

This runbook requires explicit production approval. Do not manually delete
Kyverno resources. Stop on any failed or unknown gate.

## Preflight

1. Run `refresh-project-context` and read `.codex/context/live-cluster.md`.
2. Confirm AWS account `197826770971`, expected identity, tunnel, and context.
3. Confirm `native-admission-policies` is Synced/Healthy and both bindings are `Deny`.
4. Confirm `techx-tf3` is PSA Restricted enforce and `observability-system` has no enforce label.
5. Run the good and negative server-side dry-run fixtures.
6. Render production Helm values and run server-side dry-run for workload objects.
7. Require non-zero checkout traffic and healthy checkout, browse, cart, and frontend-latency evidence.

## Reconcile

After separate approval, reconcile only `gitops/bootstrap/application.yaml` so
the live root Application receives the repo-declared automated prune/self-heal
policy. Let Argo prune wave 20 before wave 10. Do not use selective sync, force,
replace, or manual deletion.

## Stop conditions

- wave 20 prune fails or remains terminating;
- any native rejection fixture is unexpectedly admitted;
- the good fixture is rejected;
- any Argo control-plane pod becomes unready;
- workload readiness or customer SLO evidence degrades;
- any required observation is unavailable.

## Completion

Verify that Kyverno Applications, workloads, webhooks, policies, exceptions,
and Kyverno-owned CRDs are gone; all retained Applications are Synced/Healthy;
`argocd-self` latest operation is Succeeded; native admission remains enforced;
workloads are Ready; smoke probes return 200; and SLO evidence remains healthy.
```

- [ ] **Step 4: Check documentation consistency**

Run:

```bash
rg -n 'Kyverno.*remain|retain.*Kyverno|verifyImages' \
  docs/adr/0010-mandate-05-runtime-hardening.md \
  docs/evidence/mandate-05/native-migration-20260721.md \
  docs/runbooks/mandate-05-kyverno-retirement.md
rg -n 'T[B]D|T[O]DO|not yet designed' \
  docs/adr/0010-mandate-05-runtime-hardening.md \
  docs/evidence/mandate-05/native-migration-20260721.md \
  docs/runbooks/mandate-05-kyverno-retirement.md || true
git diff --check
```

Expected: every Kyverno retention statement is either explicitly historical/superseded or replaced by the webhook-plus-VAP boundary; no placeholder remains; diff check is clean.

- [ ] **Step 5: Commit the decision record and runbook**

```bash
git add docs/adr/0010-mandate-05-runtime-hardening.md \
  docs/evidence/mandate-05/native-migration-20260721.md \
  docs/runbooks/mandate-05-kyverno-retirement.md
git commit -m "docs: record native Mandate 05 retirement gates"
```

---

### Task 5: Run repository and live read-only preflight verification

**Files:**
- Verify only; no repository modification expected.

**Interfaces:**
- Consumes: the complete implementation branch.
- Produces: evidence that the PR is safe to review and a crisp GO/NO-GO for merge; it does not produce authorization to reconcile production.

- [ ] **Step 1: Run the local regression suite**

Run:

```bash
python3 -m pytest --collect-only -q scripts/ci
python3 -m pytest -q scripts/ci
python3 -m pytest scripts/ci/test_mandate05_native_retirement_contract.py -q
kubectl apply --dry-run=client -f gitops/policies/native/mandate-05-runtime-policy.yaml
kubectl apply --dry-run=client -f gitops/apps/argocd-self-app.yaml
git diff origin/main...HEAD --check
```

Expected: pytest collection succeeds, all tests pass, both manifests pass client dry-run, and diff check is clean.

- [ ] **Step 2: Render the exact production chart**

Run:

```bash
helm dependency build "phase3 - information/techx-corp-chart"
helm lint "phase3 - information/techx-corp-chart" \
  -f "phase3 - information/techx-corp-chart/values.yaml" \
  -f "phase3 - information/deploy/values-flagd-sync.yaml" \
  -f "phase3 - information/deploy/values-prod.yaml" \
  -f "phase3 - information/deploy/values-aio-llm.yaml"
helm template techx-corp "phase3 - information/techx-corp-chart" \
  --namespace techx-tf3 \
  -f "phase3 - information/techx-corp-chart/values.yaml" \
  -f "phase3 - information/deploy/values-flagd-sync.yaml" \
  -f "phase3 - information/deploy/values-prod.yaml" \
  -f "phase3 - information/deploy/values-aio-llm.yaml" \
  >/tmp/techx-production-rendered.yaml
test -s /tmp/techx-production-rendered.yaml
```

Expected: dependency build, lint, and template succeed with a non-empty render.

- [ ] **Step 3: Refresh live context and run only server-side dry-run evidence**

Run the repo `refresh-project-context` skill first. After identity/tunnel/context verification, run:

```bash
kubectl apply --dry-run=server -f docs/evidence/mandate-05/native-rejection-demo/good-native-compliant-pod.yaml
kubectl apply --dry-run=server -f docs/evidence/mandate-05/native-rejection-demo/bad-root-pod.yaml
kubectl apply --dry-run=server -f docs/evidence/mandate-05/native-rejection-demo/bad-latest-image-pod.yaml
kubectl apply --dry-run=server -f docs/evidence/mandate-05/native-rejection-demo/bad-implicit-latest-pod.yaml
kubectl apply --dry-run=server -f docs/evidence/mandate-05/native-rejection-demo/bad-first-party-tag-pod.yaml
kubectl apply --dry-run=server -f docs/evidence/mandate-05/native-rejection-demo/bad-missing-resources-pod.yaml
```

Expected: good fixture accepted; bad-root denied by PSA; remaining bad fixtures denied by the named native VAPs. No object is persisted.

- [ ] **Step 4: Review the final branch diff**

Run:

```bash
git status --short --branch
git diff --stat origin/main...HEAD
git diff --name-status origin/main...HEAD
git log --oneline --decorate origin/main..HEAD
```

Expected changed scope: contract test, Kyverno deletions, `argocd-self`, ADR/evidence, runbook, and the approved design/plan only. No secret, workload, Terraform, or unrelated file appears.

- [ ] **Step 5: Request fresh code review**

Invoke `superpowers:requesting-code-review`. Treat any finding affecting admission coverage, prune order, rollback, or production evidence as blocking.

---

### Task 6: Push and open the implementation PR

**Files:**
- No additional file changes unless review identifies a defect.

**Interfaces:**
- Consumes: all passing verification and review gates.
- Produces: a reviewable PR; it does not reconcile production.

- [ ] **Step 1: Rebase or rebuild on the newest `origin/main` if it moved**

Run:

```bash
git fetch origin --prune
git log --oneline --left-right HEAD...origin/main
```

Expected: no unreviewed upstream conflict. If `origin/main` moved, re-run all verification after integrating it.

- [ ] **Step 2: Push the task branch**

```bash
git push -u origin HEAD
```

- [ ] **Step 3: Open a non-draft PR**

Use this PR title:

```text
chore: complete native Mandate 05 Kyverno retirement
```

Use this PR body:

```markdown
## Summary

- remove the remaining Mandate 05 Kyverno policy Application, policies, and stale tests
- lock native VAP/PSA coverage with a CI contract
- use Server-Side Apply for Argo self-management
- document the future Mandate 10 webhook-plus-VAP boundary and approval-gated retirement runbook

## Safety

- no production mutation in this PR
- `observability-system` remains PSA warn/audit only
- `kube-system` remains excluded from native VAP bindings
- ExternalSecret drift is intentionally out of scope
- production bootstrap reconciliation requires separate approval after merge

## Verification

- Python CI suite
- native retirement contract
- Kubernetes client dry-runs
- exact production Helm lint/render
- live server-side dry-run rejection fixtures
- fresh code review
```

- [ ] **Step 4: Stop before production**

Report the PR URL and exact verification evidence. Do not run the reconcile section of the runbook until the PR is merged and the user explicitly approves production reconciliation.

---

### Task 7: Post-merge monitored retirement — separately approved operation

**Files:**
- No repository edits expected.

**Interfaces:**
- Consumes: merged PR, healthy Argo reconciliation inputs, explicit production approval, and the committed runbook.
- Produces: live Kyverno retirement and verified clean GitOps state, or a stopped/rolled-back operation with evidence.

- [ ] **Step 1: Obtain explicit approval and refresh all live gates**

Do not infer approval from PR merge. Re-run `refresh-project-context`, admission dry-runs, readiness, Argo control-plane checks, smoke probes, and non-zero-traffic SLO queries.

- [ ] **Step 2: Reconcile the bootstrap root only through the approved path**

Apply/reconcile `gitops/bootstrap/application.yaml` only as authorized so the live root Application receives automated prune/self-heal. Do not selectively sync child resources and do not manually delete anything.

- [ ] **Step 3: Observe wave-20 then wave-10 prune behavior**

Expected: `kyverno-policies` prunes first; only after it completes may the removed `kyverno` controller Application prune. Stop on a stuck finalizer, failed operation, or unhealthy Argo component.

- [ ] **Step 4: Prove completion across independent lanes**

Verify:

```bash
kubectl -n argocd get applications.argoproj.io
kubectl -n kyverno get all 2>&1 || true
kubectl get validatingwebhookconfigurations,mutatingwebhookconfigurations | rg kyverno || true
kubectl get clusterpolicies.kyverno.io,policyexceptions.kyverno.io -A 2>&1 || true
kubectl get validatingadmissionpolicies,validatingadmissionpolicybindings
kubectl get ns --show-labels
```

Also verify workload readiness, recent warning events, storefront/product HTTP 200 probes, and checkout/browse/cart/frontend-latency SLO evidence with non-zero traffic.

- [ ] **Step 5: Declare success only if GitOps is genuinely clean**

Required result: all intentionally retained Applications Synced/Healthy, no `requiresPruning`, latest `argocd-self` operation Succeeded, no Kyverno runtime/admission objects, native controls still enforced, workloads Ready, and customer-path evidence healthy.

The separate `flagd-secret-sync` ExternalSecret drift may still prevent the whole Argo estate from being clean. If so, report Kyverno retirement as complete but overall GitOps as PARTIAL until that dedicated remediation lands.
