# Mandate 16 — Song song hoá `prepOrderItems` để giảm latency Checkout

**Mã:** MANDATE-16
**Trụ:** Performance Efficiency
**Owner:** CDO01-Thuy Trang
**Trạng thái:** ✅ Đã implement — chờ rebuild image + evidence Jaeger
**File thay đổi:** `src/checkout/main.go`
**Liên quan:** Directive #16 yêu cầu #2 / REL-05 / postmortem 0010

---

## 1. Bối cảnh và vấn đề

### Vấn đề gốc

Hàm `prepOrderItems()` trong `checkout/main.go` xử lý **tuần tự** từng sản phẩm trong giỏ hàng:

```
for mỗi sản phẩm:
    ProductCatalogService.GetProduct(...)  ← RPC 1
    CurrencyService.Convert(...)           ← RPC 2 (phụ thuộc RPC 1)
    out[i] = OrderItem
```

Với giỏ hàng 3 sản phẩm, Jaeger trace hiện tại cho thấy:

```
──── GetProduct(item1) ────
                           ──── Convert(item1) ────
                                                   ──── GetProduct(item2) ────
                                                                              ──── Convert(item2) ────
                                                                                                      ──── GetProduct(item3) ────
                                                                                                                                 ──── Convert(item3) ────
```

**Hậu quả:**
- Latency `PlaceOrder` tăng **tuyến tính** theo số sản phẩm trong giỏ
- Với giỏ N sản phẩm: `total_latency ≈ N × (GetProduct_latency + Convert_latency)`
- Đây đúng dạng lỗi Directive #16 mô tả: *"gọi downstream tuần tự đáng lẽ song song"*

### Vì sao không cần thêm tài nguyên

`GetProduct` và `Convert` của **các sản phẩm khác nhau độc lập hoàn toàn** — không có data dependency giữa item1 và item2. Bottleneck là code structure (for-loop đồng bộ), không phải thiếu CPU/memory. Sửa code là đủ.

---

## 2. Giải pháp đã implement

### Thiết kế

Chuyển from-loop sang `errgroup` — mỗi sản phẩm chạy trong 1 goroutine độc lập:

```
goroutine 0: ──── GetProduct(item1) ──── Convert(item1) ────
goroutine 1: ──── GetProduct(item2) ──── Convert(item2) ────
goroutine 2: ──── GetProduct(item3) ──── Convert(item3) ────
             ════════════════════════════════════════════════ errgroup.Wait()
```

Trace Jaeger sau khi deploy sẽ cho thấy các span **overlap theo thời gian**:

```
GetProduct(item1) ──────────────────
GetProduct(item2) ──────────────────
GetProduct(item3) ──────────────────
Convert(item1)          ───────────
Convert(item2)          ───────────
Convert(item3)          ───────────
```

`total_latency ≈ max(GetProduct_latency) + max(Convert_latency)` thay vì tổng cộng dồn.

### Code diff

**Import — thêm `errgroup`, giữ `sync` (vẫn cần cho `sync.Once`):**

```go
// TRƯỚC
import (
    "sync"
    // ... các import khác
)

// SAU
import (
    "sync"
    "golang.org/x/sync/errgroup"   // THÊM
    // ... các import khác
)
```

**Hàm `prepOrderItems` — full diff:**

```go
// TRƯỚC — xử lý tuần tự từng item
func (cs *checkout) prepOrderItems(
    ctx context.Context,
    items []*pb.CartItem,
    userCurrency string,
) ([]*pb.OrderItem, error) {

    out := make([]*pb.OrderItem, len(items))

    for _, item := range items {
        product, err := cs.productCatalogSvcClient.GetProduct(ctx, ...)
        if err != nil { return nil, ... }

        price, err := cs.convertCurrency(ctx, product.GetPriceUsd(), userCurrency)
        if err != nil { return nil, ... }

        out[i] = &pb.OrderItem{Item: item, Cost: price}
    }

    return out, nil
}
```

```go
// SAU — xử lý song song, mỗi item 1 goroutine
func (cs *checkout) prepOrderItems(
    ctx context.Context,
    items []*pb.CartItem,
    userCurrency string,
) ([]*pb.OrderItem, error) {

    out := make([]*pb.OrderItem, len(items))

    g, ctx := errgroup.WithContext(ctx)

    for i, item := range items {
        i := i
        item := item

        g.Go(func() error {
            product, err := cs.productCatalogSvcClient.GetProduct(
                ctx,
                &pb.GetProductRequest{Id: item.GetProductId()},
            )
            if err != nil {
                return fmt.Errorf("failed to get product #%q", item.GetProductId())
            }

            price, err := cs.convertCurrency(ctx, product.GetPriceUsd(), userCurrency)
            if err != nil {
                return fmt.Errorf(
                    "failed to convert price of %q to %s",
                    item.GetProductId(),
                    userCurrency,
                )
            }

            out[i] = &pb.OrderItem{Item: item, Cost: price}
            return nil
        })
    }

    if err := g.Wait(); err != nil {
        return nil, err
    }

    return out, nil
}
```

### Điểm đảm bảo correctness

| Yêu cầu | Cách đảm bảo |
|---|---|
| Kết quả đúng thứ tự | `out[i]` với `i` capture bằng `i := i` trước khi vào goroutine |
| 1 sản phẩm lỗi → toàn bộ fail | `errgroup.Wait()` trả lỗi đầu tiên, cancel context cho goroutine còn lại |
| Không thay đổi error message | Giữ nguyên string `"failed to get product #%q"` và `"failed to convert price of %q to %s"` |
| Không race condition | Mỗi goroutine chỉ ghi vào `out[i]` của chính nó, không goroutine nào ghi cùng index |

### Dependency mới cần thêm vào `go.mod`

`golang.org/x/sync` chứa package `errgroup`. Cần verify trong `go.mod`:

```bash
grep "golang.org/x/sync" src/checkout/go.mod
```

Nếu chưa có:
```bash
cd src/checkout
go get golang.org/x/sync@latest
go mod tidy
```

> **Lưu ý:** `golang.org/x/sync` là package chuẩn của Go ecosystem, không phải third-party —
> được maintain bởi Go team, không có rủi ro dependency.

---

## 3. Kế hoạch deploy

### Bước 1 — Verify build local

```bash
cd "phase3 - information/techx-corp-platform/src/checkout"
go build ./...
# Expected: no error
```

### Bước 2 — Rebuild image qua CI pipeline

Trigger CI workflow `build-push-ecr.yml` cho service `checkout`. Sau khi build xong, cập nhật
`imageOverride` trong `values-prod.yaml`:

```yaml
components:
  checkout:
    imageOverride:
      digest: sha256:<new-digest-from-ci>
      tag: <new-tag>-checkout
```

Commit + PR → merge → ArgoCD tự sync. **Không patch tay.**

### Bước 3 — Verify sau deploy

```bash
# Rollout hoàn thành
kubectl rollout status deploy/checkout -n techx-tf3

# Không có lỗi trong log
kubectl logs -n techx-tf3 deploy/checkout --tail=50 | grep -iE "error|panic|failed"

# Smoke test: đặt 1 đơn hàng thử
curl http://localhost:8080/product/L9ECAV7KIM   # browse
# Add to cart, checkout qua UI
```

---

## 4. Evidence cần thu thập

### Jaeger trace — DoD chính

Sau khi deploy, lấy trace của 1 lần checkout có ≥2 sản phẩm:

1. Mở `http://localhost:16686/jaeger/ui` (port-forward nếu cần)
2. Service: `checkout`, Operation: `oteldemo.CheckoutService/PlaceOrder`
3. Tìm trace có nhiều span `GetProduct` và `oteldemo.CurrencyService/Convert`
4. **Verify:** các span của các sản phẩm khác nhau **overlap theo thời gian**
   - ✅ PASS: `GetProduct(item1)` và `GetProduct(item2)` bắt đầu gần cùng lúc
   - ❌ FAIL: các span xếp đuôi nhau (sequential)

### Prometheus p99 — so sánh trước/sau

```promql
# Query Prometheus để lấy p99 PlaceOrder
histogram_quantile(0.99,
  sum by (le) (
    rate(rpc_server_duration_milliseconds_bucket{
      service_name="checkout",
      rpc_method="PlaceOrder"
    }[10m])
  )
)
```

Chạy cùng mức tải (load-generator Users = 50) trước và sau deploy, ghi lại số liệu.

**Template ghi evidence:**

| Metric | Baseline (trước) | After deploy | Delta |
|---|---|---|---|
| p95 PlaceOrder (ms) | ___ | ___ | ___ |
| p99 PlaceOrder (ms) | ___ | ___ | ___ |
| Throughput checkout (req/s) | ___ | ___ | ___ |

---

## 5. Đảm bảo hành vi lỗi (verify plan)

Test case bắt buộc trước khi đóng task:

**TC-1: 1 sản phẩm GetProduct lỗi → toàn bộ PlaceOrder fail**
- Dùng flagd inject lỗi product-catalog (nếu có flag), hoặc observe từ log khi product-catalog
  restart
- Expected: `PlaceOrder` trả `codes.Internal`, message chứa `"failed to prepare order"`

**TC-2: 1 sản phẩm Convert lỗi → toàn bộ PlaceOrder fail**
- Expected: `PlaceOrder` trả `codes.Internal`, message chứa `"failed to prepare order"`

**TC-3: Giỏ hàng nhiều sản phẩm → kết quả đúng thứ tự**
- Add 3+ sản phẩm khác nhau vào giỏ
- Checkout → verify order items khớp với giỏ (đúng product, đúng price)

---

## 6. Rủi ro và giảm thiểu

| Rủi ro | Mức độ | Giảm thiểu |
|---|---|---|
| Tăng concurrent RPC lên product-catalog/DB | Có ngưỡng định lượng | Worst-case checkout tạo `8 * N` request song song sang product-catalog khi 8 pod checkout cùng nhận giỏ trung bình `N` sản phẩm. Trần DB pool phía product-catalog là `8 pod * 20 = 160` connections, nên chỉ vượt nếu `8N > 160` tức `N > 20`. Với `N <= 10`, worst-case là 80 connections đồng thời, chưa vượt giới hạn 160. |
| Tăng concurrent RPC lên currency service | Thấp | Currency service stateless, không có state/DB |
| Race condition trên `out[]` slice | Không có | Mỗi goroutine chỉ ghi vào index riêng của mình |
| Context cancel quá sớm khi 1 item lỗi | Đã xử lý | `errgroup.WithContext` cancel context → goroutine còn lại thoát sớm qua context deadline |

---

## 7. Tiêu chí hoàn thành (DoD checklist)

- [ ] `go build ./...` trong `src/checkout` thành công (không compile error)
- [ ] `golang.org/x/sync` có trong `go.mod` và `go.sum`
- [ ] Image checkout được rebuild qua CI, digest mới được cập nhật vào `values-prod.yaml`
- [ ] ArgoCD sync thành công, pod checkout Running với image mới
- [ ] **Jaeger trace:** span `GetProduct` và `Convert` của các sản phẩm khác nhau overlap theo thời gian
- [ ] **p99 PlaceOrder** giảm so với baseline (đo cùng mức tải)
- [ ] Không có CrashLoop / 500 error sau deploy
- [ ] Hành vi lỗi giữ đúng: 1 sản phẩm lỗi → toàn bộ PlaceOrder fail
- [ ] Không tăng replica hoặc tài nguyên (đúng tinh thần tối ưu code)

---

*Tác giả: CDO01*
*Ngày: 2026-07*
*Liên quan: Directive #16 / REL-05 (connection pool product-catalog) / postmortem 0010*
