# Checkout Shipping Quote Transport Incident

**Date:** 2026-07-16
**Owner:** CDO02
**Status:** Investigated

## Summary

Two small checkout success-rate dips observed on 2026-07-16 were real checkout failures, not dashboard noise.

The failures were caused by transient transport errors in `checkout` while sending:

```text
POST http://shipping:8080/get-quote
```

This is more precise than saying "shipping failed" in general. The current evidence points to an outbound HTTP client/connection problem on the `checkout -> shipping` path, not a payment failure, not a cart failure, not a Kafka failure, and not a shipping pod crash.

## Concrete failure evidence

Frontend logs captured two matching checkout failures:

```text
2026-07-16 18:29:25 ICT
shipping quote failure: failed POST to shipping service:
Post "http://shipping:8080/get-quote": ... write: broken pipe

2026-07-16 19:27:49 ICT
shipping quote failure: failed POST to shipping service:
Post "http://shipping:8080/get-quote": EOF
```

Grafana showed the dips slightly later because the panel uses a rolling success-rate window:

```text
Observed dip windows on Grafana:
18:32-18:35 ICT
19:29-19:32 ICT
```

Prometheus spanmetrics for `checkout` `PlaceOrder`:

```text
18:25-18:37 ICT: errors ~= 1.12 / total ~= 225.85, success ~= 99.5029%
19:25-19:35 ICT: errors ~= 1.11 / total ~= 162.22, success ~= 99.3151%
18:20-19:40 ICT: errors ~= 2.02 / total ~= 1532.15, success ~= 99.8681%
```

## Trace correlation

The failing trace around `19:27:49 ICT` follows this path:

```text
load-generator
-> frontend-proxy
-> frontend POST /api/checkout
-> frontend oteldemo.CheckoutService/PlaceOrder
-> checkout oteldemo.CheckoutService/PlaceOrder
-> checkout prepareOrderItemsAndShippingQuoteFromCart
-> cart GetCart
-> product-catalog GetProduct
-> currency Convert
-> checkout POST   <-- failing span
```

The last failing span is `checkout POST`, with `error=true` and a very short duration, about `306us`.

In the checkout code, that HTTP span maps to:

```text
POST http://shipping:8080/get-quote
```

## What was ruled out

Payment:

- No matching `payment` errors were found in logs during the incident window.
- `payment` server span `oteldemo.PaymentService/Charge` did not show `STATUS_CODE_ERROR`.
- The request failed before card charge completed.

Cart:

- `cart` server spans did not show matching errors.
- The failing trace shows `cart GetCart` completed before the checkout HTTP failure.

Kafka:

- `checkout` `publish orders` did not show matching errors.
- The failing flow did not reach the publish stage.

Shipping and quote application failure:

- `shipping` pods were healthy, `Running`, and had `Restart Count: 0`.
- `shipping` service endpoints were present for both pods.
- `quote` logs around the investigation window continued to show many `POST /getquote 200` responses.
- Prometheus did not show `STATUS_CODE_ERROR` on `shipping` or `quote` server spans during the relevant windows.

Cluster instability:

- `checkout-rollout` was `Healthy`.
- No relevant `Killing`, `Evicted`, `BackOff`, or unhealthy events were found for checkout, payment, cart, shipping, or quote around the failures.

## Most likely technical explanation

The most defensible explanation from the current evidence is a transient HTTP transport failure between `checkout` and `shipping`, likely on a reused keep-alive connection or a short-lived TCP reset on the `checkout -> ClusterIP shipping` path.

Why this explanation fits:

- The failing span duration was extremely short, about `306us`, which is much more consistent with connection reuse/reset failure than normal application processing.
- Errors were `EOF` and `broken pipe`, both classic transport-level failure symptoms.
- The error appeared in `checkout` HTTP client behavior, not in `shipping` business logic or `quote` response handling.
- `checkout` currently uses `otelhttp.Post(...)`, which goes through Go's default HTTP client/transport behavior and keep-alive pooling.

## Business impact

Immediate impact was low:

- About two failed checkout requests were observed in roughly 80 minutes.
- The system recovered without intervention.

Risk remained user-facing:

- Checkout failed for affected requests.
- The failure happened before payment, so there is no evidence of "charged but no order" for this incident.

## Recommended actions

1. Add a narrow retry around `POST /get-quote` in checkout.

Use 2-3 attempts, short backoff, and only retry transport-like temporary failures such as:

```text
EOF
broken pipe
connection reset by peer
temporary timeout
```

Do not retry the entire `PlaceOrder` flow. Retrying the whole checkout flow is the wrong boundary because it can create financial duplication risk.

2. Replace direct `otelhttp.Post(...)` usage for outbound shipping calls with a dedicated `http.Client`.

Recommended direction:

```text
Timeout: 2s-3s
ResponseHeaderTimeout: about 1s
IdleConnTimeout: 20s-30s
MaxIdleConnsPerHost: sized for expected checkout load
```

If the team wants a fast experiment to validate the stale keep-alive hypothesis, test a client for shipping calls with `DisableKeepAlives: true`. That is not the preferred long-term configuration, but it is a useful diagnostic control.

3. Improve checkout-side observability for outbound HTTP failures.

Add explicit attributes and logs such as:

```text
checkout.step=quoteShipping
dependency=shipping
http.url=http://shipping:8080/get-quote
error.kind=transport
attempt=1/2/3
```

That will make the next incident attributable from checkout logs directly, instead of inferring the failing step from a generic `checkout POST` span.

4. Do not change infrastructure first.

Current evidence does not justify immediate infrastructure changes. Shipping and quote both stayed healthy, and the issue volume was very low. If failures persist after the client-side mitigation, then a second investigation should look at:

```text
kube-proxy or conntrack behavior
endpoint churn
CPU throttling on shipping or quote
Actix keep-alive timeout behavior
node-level network resets
```
