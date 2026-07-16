# Checkout SLO Dashboard Hotfix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every Checkout SLO panel measure successful `PlaceOrder` operations instead of all spans emitted by the checkout service.

**Architecture:** Keep the existing Grafana dashboard and Prometheus spanmetrics source. Narrow only Checkout SLO selectors with the business operation label and add a focused static regression test that parses the dashboard JSON.

**Tech Stack:** Grafana dashboard JSON, PromQL, Python 3 standard library, Helm.

## Global Constraints

- Do not change Browse, Cart, application runtime, alerting, flagd, `/flagservice`, or Envoy fault injection.
- Do not patch Grafana or sync Argo CD manually.
- The checkout SLI operation is exactly `oteldemo.CheckoutService/PlaceOrder`.

---

### Task 1: Scope Checkout SLO queries to PlaceOrder

**Files:**
- Create: `scripts/tests/test_checkout_slo_dashboard.py`
- Modify: `phase3 - information/techx-corp-chart/grafana/provisioning/dashboards/slo-dashboard.json`

**Interfaces:**
- Consumes: Grafana panels containing PromQL strings in `targets[].expr`.
- Produces: a dashboard where every Checkout SLO query using `traces_span_metrics_calls_total` includes `span_name="oteldemo.CheckoutService/PlaceOrder"`.

- [ ] **Step 1: Write the failing regression test**

Create a Python standard-library test that loads the dashboard, selects panels whose title contains `Checkout` and whose expressions use `traces_span_metrics_calls_total`, asserts at least three matching expressions, and asserts each expression contains the exact `PlaceOrder` selector.

- [ ] **Step 2: Run the test and verify RED**

Run: `python3 scripts/tests/test_checkout_slo_dashboard.py`

Expected: non-zero exit with an assertion identifying an unscoped Checkout expression.

- [ ] **Step 3: Apply the minimal dashboard change**

In every matching Checkout expression, change:

```promql
{service_name="checkout"
```

to:

```promql
{service_name="checkout", span_name="oteldemo.CheckoutService/PlaceOrder"
```

Do not change other panels or dashboard presentation.

- [ ] **Step 4: Verify GREEN and dashboard validity**

Run:

```bash
python3 scripts/tests/test_checkout_slo_dashboard.py
python3 -m json.tool 'phase3 - information/techx-corp-chart/grafana/provisioning/dashboards/slo-dashboard.json' >/dev/null
```

Expected: both commands exit 0.

- [ ] **Step 5: Validate the decoded production query live**

Extract the rolling Checkout gauge expression from the parsed JSON and send it unchanged to live Prometheus through a local read-only port-forward.

Expected: Prometheus returns `status="success"`, one numeric result, and no parse error.

- [ ] **Step 6: Validate the chart render**

Run the chart's existing production `helm lint` and `helm template` commands using the same production values/parameters used by Argo CD.

Expected: lint exits 0 and rendered ConfigMap contains the `PlaceOrder` selector.

- [ ] **Step 7: Review and commit**

Confirm `git diff --check`, inspect the full diff, and commit only the plan, regression test, and dashboard hotfix with message:

```text
fix: scope checkout SLO to successful orders
```
