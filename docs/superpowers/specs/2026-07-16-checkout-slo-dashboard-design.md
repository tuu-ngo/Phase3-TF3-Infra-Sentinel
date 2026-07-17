# Checkout SLO Dashboard Hotfix Design

## Problem

The TF3 SLO dashboard calculates checkout success across every span emitted by
the `checkout` service. Errors from non-decisive child operations can therefore
consume checkout error budget even when `PlaceOrder` succeeds.

## Metric contract

The program defines checkout SLO as the percentage of successful order
placements over a rolling 24-hour window, with a target of at least 99%. The
dashboard will use the server operation
`oteldemo.CheckoutService/PlaceOrder` as the telemetry representation of one
order-placement attempt.

## Change

Add `span_name="oteldemo.CheckoutService/PlaceOrder"` to every checkout SLO
query in `slo-dashboard.json`, including the rolling gauge, trend, and error
budget panels. Browse, cart, application runtime, alerting, and incident
injection paths remain unchanged.

## Verification

- A regression check must fail against the current dashboard because checkout
  queries are not scoped to `PlaceOrder`.
- After the hotfix, every checkout SLO query must include the scope and the JSON
  must parse successfully.
- The decoded rolling-24h PromQL must execute successfully against live
  Prometheus and report the business checkout SLI.
- Helm lint and render must pass with the production values used by Argo CD.

## Delivery

Deliver through the `fix/checkout-slo-dashboard` branch and normal PR/GitOps
reconciliation. Do not patch Grafana or sync Argo CD manually.
