# ADR 0006 — Phạm vi đo "Browse" trên SLO dashboard (span nào tính, span nào không)

**Ngày:** 14/07/2026
**Người quyết định (ký):** CDO01 (qua Claude Code, xác nhận trực tiếp với team qua chat trước khi áp)
**Liên quan:** `onboarding/SLO.md`, `phase3 - information/techx-corp-chart/grafana/provisioning/dashboards/slo-dashboard.json`

---

## Bối cảnh

`SLO.md` định nghĩa **"Duyệt / tìm sản phẩm"** và **"Duyệt sản phẩm - độ trễ"** là 2 dòng SLO riêng biệt với **"Giỏ hàng"** và **"Đặt hàng (checkout)"**. Nhưng 6 panel "Browse" trên `slo-dashboard.json` (2 gauge SLO Status, 3 panel trend, 1 gauge Error Budget) đang query bằng `service_name="frontend"` **không lọc gì thêm** — gộp chung mọi span mà service `frontend` tạo ra.

Soi trực tiếp toàn bộ operation của `frontend` qua Jaeger API (`/api/services/frontend/operations`, 54 operation) phát hiện `service_name="frontend"` bao gồm cả:
- Span `SPAN_KIND_SERVER` **không thuộc Browse**: `GET /api/cart`, `POST /api/cart` (Giỏ hàng), `POST /api/checkout`, `GET /cart/checkout/[orderId]` (Checkout).
- Span `SPAN_KIND_CLIENT` (frontend gọi RA backend, vd `oteldemo.CheckoutService/PlaceOrder`) và `SPAN_KIND_INTERNAL` (`executing api route (pages) /api/checkout`, `render route (pages) /`, `resolve page components`...) — không phải "request khách gọi vào", mà là span con bên trong 1 request khác.

**Hệ quả đã quan sát thật:** trong lúc `checkout` đang gặp sự cố Kafka (xem postmortem 0003), panel "Browse — p95/p99 Latency" bị kéo lên gần chạm 1s SLO — không phải vì trang duyệt sản phẩm chậm thật, mà vì latency của `oteldemo.CheckoutService/PlaceOrder` (frontend đợi checkout) bị tính lẫn vào. Nếu không sửa, dashboard có thể báo động giả "vi phạm SLO Browse" trong khi sự cố thật đang ở Checkout — sai chỗ cần nhìn vào lúc xử lý sự cố.

## Quyết định

Thu hẹp mọi panel "Browse" về đúng `span_kind="SPAN_KIND_SERVER"` **và** allow-list các `span_name` sau (đối chiếu đúng operation thật lấy từ Jaeger, không suy đoán):

**Tính vào Browse:**

| span_name | Lý do |
|---|---|
| `GET /` | Trang chủ |
| `HEAD /` | Biến thể HEAD của trang chủ |
| `GET /product/[productId]` | Trang chi tiết sản phẩm |
| `GET /api/products/index` | Data danh sách sản phẩm |
| `GET /api/products/[productId]/index` | Data chi tiết sản phẩm (route match kiểu 1) |
| `GET /api/products/{productId}` | Data chi tiết sản phẩm (route match kiểu 2 — cùng ý nghĩa, khác cách Next.js gắn tên) |
| `GET /api/recommendations` | Gợi ý sản phẩm hiện trên trang duyệt |
| `GET /api/product-reviews/[productId]/index` | Review hiện trên trang sản phẩm |
| `GET /api/product-reviews-avg-score/[productId]/index` | Điểm trung bình review hiện trên trang sản phẩm |

**KHÔNG tính vào Browse (loại rõ ràng, thuộc SLO khác hoặc không phải trang thật):**

| span_name / nhóm | Lý do loại |
|---|---|
| `GET /cart`, `GET /api/cart`, `POST /api/cart` | Thuộc SLO **Giỏ hàng** |
| `POST /api/checkout`, `GET /cart/checkout/[orderId]` | Thuộc SLO **Checkout** |
| `POST /api/product-ask-ai-assistant/...`, `oteldemo.ProductReviewService/AskProductAIAssistant` | `SLO.md` ghi rõ tóm tắt AI là "best-effort, không SLA cứng" — tách riêng, không gộp vào Browse |
| `GET /_error`, `HEAD /_error`, `render route (pages) /_error` | Trang lỗi Next.js, không phải trang thật khách xem |
| Mọi `oteldemo.*Service/*` (CLIENT), `executing api route...`/`render route...`/`resolve page components` (INTERNAL), `dns.lookup`, `tcp.connect` | Span nội bộ/hạ tầng bên trong 1 request khác, không phải request khách gọi trực tiếp vào |
| `GET`, `POST`, `HEAD` (không tham số, generic) | Không rõ route thật, khả năng là static asset/route chưa match — loại để tránh lẫn |

**Tạm loại, chưa đủ dữ kiện xác nhận (để ngỏ, review lại sau nếu cần):**

| span_name | Lý do tạm loại |
|---|---|
| `GET /api/currency` | Thao tác đổi hiển thị tiền tệ — không phải "duyệt/tìm sản phẩm" theo đúng nghĩa `SLO.md`, dù có thể xảy ra trong lúc duyệt |
| `GET /api/data` | Chưa xác nhận được trang nào gọi endpoint này |
| `GET /api/shipping` | Chưa xác nhận được có thuộc luồng duyệt sản phẩm hay là 1 phần của luồng checkout (ước tính phí ship) |

## Đã áp dụng

Sửa `service_name="frontend"` trong 9 chỗ `expr` (6 panel Browse) thành:

```promql
service_name="frontend", span_kind="SPAN_KIND_SERVER", span_name=~"GET /|HEAD /|GET /product/\[productId\]|GET /api/products/index|GET /api/products/\[productId\]/index|GET /api/products/\{productId\}|GET /api/recommendations|GET /api/product-reviews/\[productId\]/index|GET /api/product-reviews-avg-score/\[productId\]/index"
```

Đã verify trực tiếp trên Prometheus live trước khi áp: query sau khi lọc trả **2.74 req/s**, so với **11.57 req/s** của query cũ không lọc — xác nhận filter loại bỏ đúng phần traffic không thuộc Browse (checkout/cart/internal spans), không phải lỗi regex làm rỗng dữ liệu.

⚠️ **Bẫy escaping khi sửa file JSON này (đã dính 1 lần, ghi lại để không lặp lại):** để regex match đúng ký tự `[`/`]`/`{`/`}` theo nghĩa đen (không phải ký tự đặc biệt của regex), file `.json` phải viết **4 dấu `\`** liên tiếp trước mỗi ký tự đó (vd `\\\\[productId\\\\]`), không phải 2. Lý do: JSON decode bóc 1 lớp escape (4 dấu `\` → còn 2), rồi PromQL tự thân cũng escape chuỗi kiểu Go string literal nên bóc thêm 1 lớp nữa (2 dấu `\` → còn 1) — chỉ còn đúng 1 dấu `\` tới được regex engine, khớp cú pháp regex cần. Viết 2 dấu `\` (tưởng là đủ) sẽ qua được JSON nhưng PromQL báo lỗi `unknown escape sequence` vì `\[` không phải escape hợp lệ trong string literal của nó — toàn bộ panel liên quan sẽ hiện "No data" dù JSON vẫn valid. Trước khi commit, luôn test bằng cách `json.load()` file lấy đúng `expr` đã decode rồi gửi thẳng chuỗi đó cho Prometheus API — không test bằng chuỗi gõ tay trong terminal, vì sẽ thiếu đúng 1 lớp escape mà chỉ JSON thật mới tạo ra.

## Việc còn để ngỏ

- [ ] Xác nhận `GET /api/currency`, `GET /api/data`, `GET /api/shipping` có nên tính vào Browse không — hiện đang loại theo hướng thận trọng (chỉ tính cái chắc chắn), review lại sau nếu cần.
- [ ] Cân nhắc áp cùng nguyên tắc lọc `span_kind="SPAN_KIND_SERVER"` cho panel Cart/Checkout nếu phát hiện chúng cũng đang bị lẫn span nội bộ tương tự (chưa kiểm tra kỹ, chỉ mới phát hiện và sửa ở Browse).
- [ ] Nếu sau này có route Browse mới (vd trang search riêng, trang category), phải bổ sung thủ công vào allow-list — đây là đánh đổi đã chọn (allow-list an toàn hơn deny-list, tránh route lạ tự động lọt vào Browse, nhưng route mới hợp lệ sẽ bị loại nhầm cho tới khi ai đó cập nhật danh sách).
