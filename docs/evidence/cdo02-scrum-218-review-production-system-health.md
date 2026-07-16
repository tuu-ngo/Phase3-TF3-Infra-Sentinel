# SCRUM-218 - Review Production System Health And Incident Signals

Ngay cap nhat: 2026-07-16
Phu trach: CDO02

## Scope

Kiem tra production thuc te de xac dinh service nao dang on, service nao co dau hieu degrade, va su co nam o lop pod, rollout, log hay dependency chain.

## Evidence

- Checkout rollout runbook:
  [docs/runbooks/checkout-argo-rollouts-canary.md](C:/Users/Admin/Desktop/xbrain-phase-3/Phase3-TF3-Infra-Sentinel/docs/runbooks/checkout-argo-rollouts-canary.md)
- Checkout health/dependency code:
  [phase3 - information/techx-corp-platform/src/checkout/main.go](C:/Users/Admin/Desktop/xbrain-phase-3/Phase3-TF3-Infra-Sentinel/phase3%20-%20information/techx-corp-platform/src/checkout/main.go:145)
- Product catalog source:
  [phase3 - information/techx-corp-platform/src/product-catalog/main.go](C:/Users/Admin/Desktop/xbrain-phase-3/Phase3-TF3-Infra-Sentinel/phase3%20-%20information/techx-corp-platform/src/product-catalog/main.go)
- Postmortem lien quan checkout/Kafka:
  [docs/postmortem/0003-checkout-kafka-producer-latency-incident.md](C:/Users/Admin/Desktop/xbrain-phase-3/Phase3-TF3-Infra-Sentinel/docs/postmortem/0003-checkout-kafka-producer-latency-incident.md)

## Outcome

- Xac nhan cluster khong sap toan cuc.
- Ghi nhan checkout tung readiness fail `NOT_SERVING`.
- Ghi nhan `product-catalog` co nhieu `DeadlineExceeded`, can tiep tuc theo doi/sua.
- Ghi nhan them Kyverno `PolicyViolation` tren nhieu workload observability va data path.
