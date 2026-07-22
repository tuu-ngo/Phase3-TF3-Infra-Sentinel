# ADR 0011 - Mandate 16: Checkout Latency Optimization

**Ngay:** 2026-07-22  
**Nguoi quyet dinh:** CDO01-Thuy Trang / TF3 Performance Efficiency  
**Reviewer/phoi hop:** TF3 platform owner, CDO02, mentor  
**Trang thai:** Accepted; ready for mentor review  
**Evidence:** [`docs/docx_cdo01/mandate-16-parallelize-checkout-prep-order-items.md`](../docx_cdo01/mandate-16-parallelize-checkout-prep-order-items.md), [`docs/mandate-16-checkout-latency-optimization.md`](../mandate-16-checkout-latency-optimization.md)

---

## Context

Mandate 16 yeu cau giam tail latency tren luong **browse -> cart -> checkout**, voi trong tam la `checkout.PlaceOrder`, ma khong tang tai nguyen runtime hoac thay doi topology production.

Trace truoc toi uu cho thay bottleneck nam o buoc checkout preparation. Sau khi doc cart, checkout enrich tung item theo chuoi `ProductCatalogService/GetProduct` va `CurrencyService/Convert`. Cac item khac nhau doc lap voi nhau, nhung code cu xu ly noi duoi, lam latency tang theo so san pham trong gio hang.

## Decision

Chap nhan toi uu checkout preparation bang cach song song hoa cac tac vu doc lap:

1. Chay item enrichment song song voi shipping quote sau khi cart da duoc doc.
2. Xu ly cac cart item doc lap dong thoi trong `prepOrderItems`.
3. Giu thu tu output on dinh va giu hanh vi all-or-nothing khi mot item loi.
4. Bo qua currency conversion RPC khi source currency da trung target currency.
5. Khong thay doi manifest, HPA, rollout, node pool, network policy hoac flagd.

## Latency Budget

| Scope | Budget | Result |
|---|---:|---|
| Browse p95/p99 | <= 200ms / <= 600ms | Dat theo Locust va Product Catalog metric |
| Cart p95/p99 | <= 200ms / <= 600ms | Dat theo Locust va CartService metric |
| Checkout server-side p99 | < 300ms | Dat: **198ms** |
| Checkout p95 guardrail | <= 250ms | Dat: **74.6ms** server-side; **210ms** HTTP Locust |
| Resource constraint | Khong tang runtime capacity | Dat theo evidence replica/CPU hien co |

## Evidence Summary

| Evidence | Before | After / Current | Ket qua |
|---|---:|---:|---|
| Checkout p95 server-side | 155ms | 74.6ms | -80.4ms |
| Checkout p99 server-side | 355ms | 198ms | -157ms |
| Locust `POST /api/checkout` p95 | baseline 270ms | 210ms current | Dat guardrail |
| Locust `POST /api/checkout` p99 | baseline 940ms | 15000ms current aggregate | Bi anh huong failure/outlier tich luy, khong dung lam bang chung chinh |
| CartService `GetCart` p95/p99 | - | ~4.81ms / ~5.37ms | On dinh |
| ProductCatalog `GetProduct` p95/p99 | 4.89ms / 16.4ms | ~4.84ms / ~13.83ms | Khong regression |
| Trace duration cung order 10 san pham | 1.44s | 1.17s | -270ms |
| Trace span count cung order 10 san pham | 120 | 104 | -16 span |
| Checkout CPU | ~25m | ~8m | Khong tang |
| Checkout replicas | 2 | 2 | Khong scale-up |

Locust current table van ghi 251 fail tich luy tren `POST /api/checkout`, lam p99 HTTP tang len 15000ms. Tai thoi diem chup, header Locust hien **Failures 0%** va current failures/s bang **0**. Do do, ADR dung Prometheus server-side latency va Jaeger trace lam evidence chinh cho optimization, dong thoi ghi ro outlier/failure o HTTP layer de mentor audit duoc.

## Consequences

Positive:

- Checkout khong con cong don latency item enrichment theo cart size.
- Server-side checkout p99 xuong duoi budget `<300ms`.
- Cart va Product Catalog khong co dau hieu regression sau khi checkout tang song song hoa.
- Khong mua latency bang replica, CPU, memory hoac node.

Trade-offs:

- Downstream RPC concurrency co the tang khi cart rat lon.
- Logic checkout phuc tap hon vong lap tuan tu cu.
- HTTP p99 Locust phai duoc doc can than vi bang cong don co the bi outlier/failure cu keo lech.

Mitigation:

- Giu item order on dinh va hanh vi fail-fast/all-or-nothing.
- Theo doi Product Catalog, Currency va checkout failure rate trong demo.
- Neu mentor bat buoc node count, dung Grafana node panel hoac SRE vi `kubectl get nodes` bi RBAC readonly chan.

## Final Decision

Giu implementation hien tai cho Mandate 16. Evidence du de nop mentor review voi ket luan: bottleneck da duoc xu ly bang toi uu code, checkout server-side tail latency giam ro, va khong tang tai nguyen runtime.

---

*Ky: CDO01-Thuy Trang*
