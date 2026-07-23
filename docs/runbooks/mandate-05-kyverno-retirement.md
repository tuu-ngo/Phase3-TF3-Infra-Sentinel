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
