# ADR 0011 - Mandate 16 Checkout Latency Optimization

**Date:** 2026-07-23

**Decision owner:** CDO02 Reliability/Cost

**Collaborators/reviewers:** CDO01, mentor

**Status:** Accepted for implementation and evidence collection

**Related:** Mandate 16, `docs/mandate-16-checkout-latency-optimization.md`

## Context

Mandate 16 requires reducing checkout tail latency under sustained load without buying performance through more pods, more nodes, or topology changes.

Trace and code review on `checkout.PlaceOrder` showed that the checkout critical path was longer than necessary because multiple independent steps were still executed serially.

The implementation that went into `phase3 - information/techx-corp-platform/src/checkout/main.go` actually addressed three separate bottlenecks, not just one aggregated "checkout preparation" issue.

## Bottlenecks Identified

### Bottleneck 1: item preparation and shipping quote were serialized

After the cart was loaded, `prepareOrderItemsAndShippingQuoteFromCart` executed:

1. `prepOrderItems(...)`
2. `quoteShipping(...)`

These two branches both depend on the cart, but they do not depend on each other. Running them in sequence stretched the checkout critical path unnecessarily.

### Bottleneck 2: each cart item was enriched one-by-one

Inside `prepOrderItems`, each line item performed:

1. `product-catalog.GetProduct`
2. `currency.Convert`

before moving to the next item. On larger carts, latency accumulated roughly with cart size instead of converging on the slowest independent branch.

### Bottleneck 3: redundant currency conversion RPCs

`convertCurrency` still called the currency service even when no conversion was needed, especially for the common `USD -> USD` path used by catalog prices and shipping quotes.

That added avoidable network hops, spans, and latency to the critical path.

## Decision

We will keep the Mandate 16 implementation as a code-path optimization with three explicit changes:

1. Run `prepOrderItems(...)` and `quoteShipping(...)` in parallel after the cart is loaded.
2. Run per-item enrichment concurrently inside `prepOrderItems(...)`, while preserving output order by writing back to the original item index.
3. Short-circuit `convertCurrency(...)` when the input is nil, the target currency is empty, or the source and target currency already match.

## Scope

- Service: `checkout`
- Code path: `checkout.PlaceOrder`
- Main implementation file: `phase3 - information/techx-corp-platform/src/checkout/main.go`
- Evidence file: `docs/mandate-16-checkout-latency-optimization.md`

## Why This Is the Right Boundary

This decision deliberately optimizes latency by removing unnecessary serialization in the checkout request path.

It does not:

- increase replicas
- change HPA behavior
- change node pools
- change rollout strategy
- change network topology
- change checkout business rules

That keeps the fix aligned with Mandate 16: faster under load, but not by adding capacity.

## Consequences

### Positive

- The checkout critical path is shorter because independent branches no longer wait on each other.
- Tail latency becomes less sensitive to cart size because item preparation no longer accumulates strictly linearly.
- Common no-op currency paths stop paying for an unnecessary RPC.
- The change remains narrow and low-risk because it stays inside one service and one request path.

### Trade-offs

- Concurrent downstream calls increase short bursts of fan-out to `product-catalog` and `currency` for larger carts.
- The code path is more concurrent and therefore slightly harder to reason about than the previous sequential loop.

### Mitigations

- Output order is preserved by writing results to the original slice index.
- Error handling remains fail-fast at the request level: if item preparation fails, checkout still fails instead of returning partial data.
- Scope stays limited to code; no production infrastructure tuning is mixed into this change.

## Rollback

- Revert the checkout code-path optimization only.
- Keep production manifests, rollout settings, node pools, and autoscaling configuration unchanged.
- Re-run the existing checkout verification path after rollback to confirm behavior returns to the pre-optimization baseline.

## Evidence Expectations

This ADR should be defended with:

1. before/after traces showing overlap of independent spans
2. before/after p95 and p99 for checkout under sustained load
3. proof that no additional runtime capacity was introduced

The implementation note and evidence pack live in:

- `docs/mandate-16-checkout-latency-optimization.md`

## Final Position

Mandate 16 is not a single bottleneck fix. It is a focused optimization package over three related latency bottlenecks in the same checkout path:

1. serialized order-item preparation vs shipping quote
2. serialized per-item enrichment
3. redundant currency conversion RPCs

We accept this design because it reduces checkout latency in the narrowest safe place, without changing production topology or buying speed through extra infrastructure.
