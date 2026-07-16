# ADR 0005 - Accepted Risk for Postgres/Kafka Local State While REL-10 Only Fixes Valkey

**Date:** 2026-07-13
**Decision Makers:** CDO02
**Status:** Accepted

## Context

Week 2 reliability work includes `REL-10`: stop losing shopping carts when `valkey-cart`
restarts. Runtime evidence and backlog analysis show the broader problem is bigger:
`postgresql` and `kafka` are also still running without persistent volumes in this demo
platform.

The cart-loss path has already happened in incident history (`INC-2`), so it is the
highest-value stateful fix we can land quickly inside the current mandate. By contrast,
adding ad-hoc persistence to Postgres or Kafka this late would be a much riskier change:
it alters shared infrastructure behavior, needs careful migration planning, and overlaps
with the longer-term managed-services direction already captured in ADR 0002.

## Decision

We will:

1. Enable persistent storage for `valkey-cart` now.
2. Explicitly accept the remaining short-term risk for local-state `postgresql` and `kafka`.
3. Keep Postgres/Kafka persistence or managed-service migration as follow-up work, not an
   unplanned week-2 infra change.

## Consequences

- Positive:
  - Fixes the incident-backed cart-loss path with a contained change.
  - Reduces ArgoCD/node-drain/restart risk for the shopping cart immediately.
  - Avoids rushing a high-blast-radius data migration under time pressure.

- Negative:
  - Postgres and Kafka still remain accepted risks if the pod or node is lost.
  - This is not a full stateful-HA solution; it is a scoped week-2 mitigation.

## Follow-up

- Track full Postgres/Kafka persistence or managed-service migration under the existing
  backlog / ADR 0002 path.
- Revisit this ADR once the team has a mandate to change shared stateful infrastructure.
