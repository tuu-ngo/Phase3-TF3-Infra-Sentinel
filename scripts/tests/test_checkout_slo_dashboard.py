#!/usr/bin/env python3
"""Regression check for the business Checkout SLO query scope."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD = ROOT / (
    "phase3 - information/techx-corp-chart/grafana/provisioning/"
    "dashboards/slo-dashboard.json"
)
PLACE_ORDER_SELECTOR = 'span_name="oteldemo.CheckoutService/PlaceOrder"'


def main() -> None:
    dashboard = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    checkout_expressions = [
        expression
        for panel in dashboard["panels"]
        if "Checkout" in panel.get("title", "")
        for target in panel.get("targets", [])
        if "traces_span_metrics_calls_total"
        in (expression := target.get("expr", ""))
    ]

    assert len(checkout_expressions) >= 3, (
        "expected checkout gauge, trend, and error-budget expressions"
    )

    unscoped = [
        expression
        for expression in checkout_expressions
        if PLACE_ORDER_SELECTOR not in expression
    ]
    assert not unscoped, (
        f"{len(unscoped)} Checkout SLO expressions are not scoped to PlaceOrder"
    )

    print(
        f"PASS: {len(checkout_expressions)} Checkout SLO expressions "
        "are scoped to PlaceOrder"
    )


if __name__ == "__main__":
    main()
