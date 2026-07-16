# ADR 0010 — Mandate 05: Runtime Admission Hardening

**Date:** 2026-07-17

**Decision owner:** CDO01 / TF3 Security

**Collaborators/reviewers:** TF3 platform owner, CDO02, mentor

**Status:** Draft for PR 0 / PR 1 preparation

## Context

Mandate 05 closes the remaining runtime admission gaps for `techx-tf3` without changing flagd, incident injection, or the public storefront boundary. The production chart is GitOps-managed through Argo CD, so policy changes must be introduced in Audit first, with exact exceptions documented before any Enforce step.

## Decision

1. Use the authoritative production render with all four Argo CD values files.
2. Keep Kyverno policies in Audit until each rule has an explicit test and evidence path.
3. Enforce CPU/memory resource requirements for containers and initContainers, but not ephemeral containers.
4. Enforce baseline security context for first-party workloads, with exact-label operational exceptions recorded in the exception register.
5. Enforce no-latest and first-party digest pinning separately from security policies.
6. Keep PM-101 signing and Trivy evidence as provenance input for first-party digest promotion.

## Scope

- Namespace: `techx-tf3`
- First-party application set: the 18 application workloads defined in the mandate spec.
- Operational/third-party workloads: handled separately with exact-label exceptions and review dates.

## Exceptions

Approved exceptions must be exact label matches on `app.kubernetes.io/name`, with an owner, reason, remediation plan, and review date. Current draft exceptions are recorded in `docs/evidence/mandate-05/exception-register.yaml`.

## Rollback

- Resource policy rollback: revert the resource policy change only.
- Security policy rollback: revert the baseline policy change only.
- Image policy rollback: revert the latest/digest policy change only.
- Workload remediation rollback: revert the workload-only values change only.

## Follow-up

This ADR becomes final when the first render/inventory pass, reconciliation script, admission tests, and runtime smoke tests are complete.
