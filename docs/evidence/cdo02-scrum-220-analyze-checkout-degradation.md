# SCRUM-220 - Analyze Checkout Degradation And Propose Fix Direction

Ngay cap nhat: 2026-07-16
Phu trach: CDO02

## Scope

Khoanh vung nguyen nhan checkout degrade trong vai gio gan day, doc code healthcheck va doi chieu log dependency de dua ra huong sua an toan truoc khi thay doi he thong.

## Evidence

- Checkout health dependency code:
  [phase3 - information/techx-corp-platform/src/checkout/main.go](C:/Users/Admin/Desktop/xbrain-phase-3/Phase3-TF3-Infra-Sentinel/phase3%20-%20information/techx-corp-platform/src/checkout/main.go:160)
- Checkout rollout manifest:
  [phase3 - information/techx-corp-chart/templates/checkout-rollout.yaml](C:/Users/Admin/Desktop/xbrain-phase-3/Phase3-TF3-Infra-Sentinel/phase3%20-%20information/techx-corp-chart/templates/checkout-rollout.yaml)
- Checkout PDB:
  [gitops/infrastructure/pdb-checkout.yaml](C:/Users/Admin/Desktop/xbrain-phase-3/Phase3-TF3-Infra-Sentinel/gitops/infrastructure/pdb-checkout.yaml)
- Graceful shutdown PR:
  <https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel/pull/136>

## Outcome

- Xac dinh checkout khong chet han ma bi degrade readiness.
- Root cause gan nhat nam o dependency health path, nghi ngo manh nhat la `product-catalog`.
- Huong sua de xuat: giam coupling cua readiness voi upstream, tach health business path khoi health local, va ra soat timeout/runtime cua `product-catalog`.
