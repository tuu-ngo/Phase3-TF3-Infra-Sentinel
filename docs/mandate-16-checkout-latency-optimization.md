# Mandate 16 - Checkout Latency Optimization

## Mục tiêu

Giảm tail latency (`p95/p99`) trên critical path của `checkout` dưới tải bền mà **không tăng tài nguyên** và **không đổi topology production**.

Directive gốc: `MANDATE-16-latency-under-load.md`

## Phạm vi thay đổi

File code chính:

- `phase3 - information/techx-corp-platform/src/checkout/main.go`
- `phase3 - information/techx-corp-platform/src/checkout/go.mod`
- `phase3 - information/techx-corp-platform/src/checkout/go.sum`

## Vấn đề được xử

Trước thay đổi, `checkout` có 3 điểm làm critical path dài hơn cần thiết:

1. Sau khi lấy giỏ hàng, `prepareOrderItemsAndShippingQuoteFromCart` chạy:
   - `prepOrderItems(...)`
   - rồi mới `quoteShipping(...)`

   Hai bước này độc lập nhưng đang bị chạy tuần tự.

2. Bên trong `prepOrderItems`, mỗi cart item lại bị enrich tuần tự:
   - gọi `product-catalog.GetProduct`
   - gọi `currency.Convert`

   Với giỏ có nhiều item, tail latency cộng dồn theo số dòng hàng.

3. `convertCurrency` vẫn gọi RPC sang `currency` ngay cả khi currency nguồn đã trùng currency đích.

## Giải pháp

### 1. Song song hóa hai bước độc lập

Trong `prepareOrderItemsAndShippingQuoteFromCart`, chạy song song:

- enrich order items
- lấy shipping quote

Điều này cắt bớt thời gian chờ trên critical path mà không đổi business flow.

### 2. Song song hóa enrich từng line item

Trong `prepOrderItems`, mỗi item được xử lý bằng goroutine riêng, nhưng vẫn ghi kết quả về đúng index ban đầu để giữ thứ tự output ổn định.

### 3. Bỏ RPC đổi tiền khi không cần

Trong `convertCurrency`, nếu:

- `from == nil`
- hoặc `toCurrency` rỗng
- hoặc `from.CurrencyCode == toCurrency`

thì trả thẳng giá trị cũ, không gọi `currency.Convert`.

Điều này đặc biệt có lợi cho case phổ biến `USD -> USD`.

## An toàn thay đổi

- Không thay đổi manifest, values, rollout, HPA, node pool hay cấu hình production.
- Không apply tay lên cluster.
- Không thay đổi business rule:
  - vẫn lấy cart
  - vẫn enrich đủ item
  - vẫn lấy shipping quote
  - vẫn charge / ship / empty cart theo flow hiện tại
- Chỉ tối ưu cách tổ chức lời gọi để giảm latency.

## Verify local

Đã verify local cho riêng module `checkout`:

```powershell
$env:PATH='C:\Program Files\Go\bin;' + $env:PATH
go test ./...
```

Kết quả:

- `github.com/open-telemetry/techx-corp/src/checkout` - pass
- `github.com/open-telemetry/techx-corp/src/checkout/kafka` - pass (no test files)
- `github.com/open-telemetry/techx-corp/src/checkout/money` - pass

## Ghi chú thêm

Trong lúc mở đường test bằng Go local, lộ ra một lỗi build cũ:

- `status.Errorf(codes.Internal, err.Error())`

đã được đổi thành:

- `status.Error(codes.Internal, err.Error())`

để module build sạch trên toolchain hiện tại.

## Verify Jaeger sau deploy

Trace Jaeger ngày 21/07/2026 xác nhận thay đổi đã đi đúng luồng:

- Sau `CartService/GetCart`, `prepOrderItems(...)` và `quoteShipping(...)` chạy overlap dưới span `prepareOrderItemsAndShippingQuoteFromCart`.
- Trong `prepOrderItems(...)`, các span `ProductCatalogService/GetProduct` và `CurrencyService/Convert` của nhiều cart item xuất hiện cùng cấp và overlap theo thời gian, thay vì nối đuôi nhau từng item.
- Bottleneck trước đây là waterfall tuần tự theo item; sau tối ưu, span `prepareOrderItemsAndShippingQuoteFromCart` quan sát được khoảng **23.97ms**, còn span `CheckoutService/PlaceOrder` khoảng **45.6ms** trong trace sau.

So với trace trước, request checkout quan sát được khoảng **185.05ms** và waterfall `GetProduct -> Convert` còn xếp đuôi theo từng item. Jaeger vì vậy cho thấy phần bottleneck trong đoạn chuẩn bị order/shipping đã giảm rõ: critical path không còn cộng dồn tuyến tính theo số sản phẩm trong giỏ, mà gần với nhánh downstream chậm nhất trong nhóm tác vụ song song.

## Kỳ vọng tác động

- Giảm số round-trip tuần tự trong critical path `checkout`
- Giảm độ nhạy của `p95/p99` theo số lượng cart items
- Không làm tăng CPU/node/runtime footprint theo kiểu “mua hiệu năng bằng tài nguyên”

## Chưa làm trong PR này

- Chưa thay đổi Grafana dashboard / SLO query
- Chưa chạy load test production
- Chưa đụng các tối ưu khác ở `frontend`, `ad`, `recommendation`

PR này cố ý giữ phạm vi nhỏ để an toàn với production đang chạy.
