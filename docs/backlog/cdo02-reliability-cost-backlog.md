# Backlog ưu tiên — CDO02 (Reliability + Cost Optimization)

**Ngày lập:** 08/07/2026
**Người lập:** arthur (CDO02)
**Trụ phụ trách:** Reliability, Cost Optimization (đã chốt draft với CDO01 — CDO01 giữ Performance Efficiency + Security)
**Công thức xếp hạng:** Ưu tiên = Rủi ro (khả năng × mức nghiêm trọng) × Tác động business (theo `onboarding/SLO.md`, `onboarding/BUDGET.md`, `onboarding/INCIDENT_HISTORY.md`)

---

## Đính chính 1 nhận định kỹ thuật trước đó (quan trọng, ảnh hưởng độ ưu tiên)

Lúc đọc code tĩnh (`techx-corp-chart/values.yaml`), tôi từng kết luận "không có `requests`, chỉ có `limits`". Kiểm tra lại trên pod thật đang chạy cho thấy **kết luận đó sai một phần**: Helm chart tự động mirror `requests = limits` cho memory khi build pod spec — mọi pod hiện có QoS `Guaranteed` cho memory (không phải `BestEffort`/`Burstable` như suy đoán). Cái thật sự thiếu là **CPU**: 28/32 container hoàn toàn không có `requests`/`limits` CPU nào. Backlog dưới đây dựa trên số liệu đã xác minh lại, không phải suy đoán ban đầu.

---

## RELIABILITY

### R1 — Toàn hệ thống chạy `replicas: 1` (SPOF ở mọi service, không riêng cart)
**Rủi ro:** Cao (khả năng cao — đã từng xảy ra ở INC-2; nghiêm trọng — mất cả service khi 1 pod chết/node bảo trì).
**Tác động business:** Rất cao — `cart`, `checkout`, `payment`, `product-catalog` đều nằm trên đường ra tiền (SLO checkout ≥99%). Mất 1 trong số này = mất doanh thu trực tiếp.
**Đề xuất:** Tăng `replicas` ≥2 cho tối thiểu các service trên đường checkout (`cart`, `checkout`, `payment`, `currency`, `product-catalog`, `shipping`), thêm `PodDisruptionBudget` đi kèm để tránh mất hết bản sao cùng lúc khi node drain.
**Chi phí:** Thấp-trung bình (nhân đôi số pod của ~6 service nhỏ, không phải toàn bộ 20 service — memory limit các service này đều nhỏ, tổng thêm vài trăm Mi).

### R2 — Health check giả trên gần như toàn bộ service
**Rủi ro:** Cao — đã xác nhận qua code: `checkout`, `product-catalog`, `recommendation`, `currency`, `product-reviews`, `ad`, `payment` đều có hàm `Check()` trả `SERVING` cố định, không kiểm tra dependency (DB/Kafka/Redis) thật.
**Tác động business:** Cao — làm mọi nỗ lực thêm readiness probe (R3) trở nên vô nghĩa; K8s vẫn route traffic vào pod dù dependency đã chết.
**Đề xuất:** Sửa `Check()` ở từng service để gọi thử dependency thật (VD `db.Ping()`) trước khi trả SERVING. Làm song song/trước R3.
**Chi phí:** Thấp — chỉ sửa logic, không tốn thêm tài nguyên.

### R3 — Không có `readinessProbe`/`livenessProbe` nào trong toàn bộ chart
**Rủi ro:** Cao — chính xác nguyên nhân gốc của INC-3 (lỗi thanh toán lúc deploy do thiếu readiness gating), **vẫn chưa được vá tới giờ**.
**Tác động business:** Cao — mỗi lần deploy/rollout có nguy cơ tái diễn INC-3.
**Đề xuất:** Thêm probe cho toàn bộ service, ưu tiên nhóm trên đường checkout trước. Phụ thuộc R2 (probe vô nghĩa nếu health check còn giả).
**Chi phí:** Thấp.

### R4 — `checkout.PlaceOrder`: charge tiền trước khi ship, không có rollback
**Rủi ro:** Trung bình (khả năng thấp hơn R1-R3 vì cần đúng lúc `shipOrder` lỗi sau khi `chargeCard` thành công) nhưng **mức nghiêm trọng rất cao** khi xảy ra — khách bị trừ tiền, đơn coi như thất bại, không hoàn tiền tự động.
**Tác động business:** Cao — ảnh hưởng trực tiếp uy tín + khiếu nại tài chính thật.
**Đề xuất:** Thêm logic bù trừ (refund/void payment) khi `shipOrder` lỗi sau `chargeCard`, hoặc đảo thứ tự gọi (ship trước, charge sau) nếu nghiệp vụ cho phép.
**Chi phí:** Thấp (chỉ sửa logic Go trong `checkout/main.go`).

### R5 — Thiếu connection pool tới Postgres ở `product-catalog` và `product-reviews`
**Rủi ro:** Cao — nguyên nhân gốc y hệt INC-1 (cạn connection DB dưới tải cao), chưa được vá: `product-catalog` không set `MaxOpenConns` (mặc định unlimited), `product-reviews` mở connection mới cho **mỗi request**.
**Tác động business:** Cao — `product-reviews` phục vụ tính năng AI chủ lực của sản phẩm (tóm tắt review); đây cũng là service dùng chung Postgres với `accounting` (vừa xảy ra sự cố thật).
**Đề xuất:** `product-catalog`: set `SetMaxOpenConns`/`SetMaxIdleConns` hợp lý. `product-reviews`: chuyển sang connection pool (`psycopg2.pool` hoặc SQLAlchemy engine) thay vì connect-per-request.
**Chi phí:** Thấp — chỉ sửa code, không cần thêm hạ tầng.

### R6 — Chưa rà soát memory limit toàn hệ thống sau sự cố `accounting`
**Rủi ro:** Trung bình — `accounting` đã OOMKilled thật 44 lần/19h (bằng chứng sống, đã vá 120Mi→350Mi). Chưa kiểm tra các service khác (VD `checkout` chỉ có 20Mi, `product-catalog` 20Mi, `currency` 20Mi) có cùng rủi ro dưới tải cao hơn load-generator hiện tại không.
**Tác động business:** Trung bình-cao nếu xảy ra ở service trên đường checkout (khác `accounting` vốn không chặn checkout).
**Đề xuất:** Load test có kiểm soát (tăng dần `LOCUST_USERS`) để tìm ngưỡng thật, điều chỉnh memory limit dựa trên số liệu, không đoán.
**Chi phí:** Trung bình (cần thời gian test).

### R7 — Không có CPU `requests`/`limits` cho 28/32 container (đã xác minh trên pod thật)
**Rủi ro:** Trung bình — không có gì ngăn 1 service ăn hết CPU node, ảnh hưởng service khác cùng node (noisy neighbor); cũng chặn khả năng bật HPA theo CPU.
**Tác động business:** Trung bình — rủi ro âm thầm, khó thấy ngay nhưng tích luỹ theo thời gian, đặc biệt khi thêm replicas (R1) làm nhiều pod cùng node hơn.
**Đề xuất:** Thêm CPU `requests`/`limits` cho toàn bộ component. Đây cũng là nền tảng bắt buộc cho C2/C4 bên dưới (Cost).
**Chi phí:** Thấp — chỉ cấu hình, nhưng cần đo trước khi đặt số cụ thể (tránh đặt bừa).

### R8 — Datastore đơn lẻ: Postgres/Valkey/Kafka mỗi loại 1 instance
**Rủi ro:** Trung bình (chưa xảy ra sự cố thật, nhưng SPOF tầng dữ liệu — nặng hơn SPOF tầng service).
**Tác động business:** Rất cao nếu xảy ra (mất toàn bộ dữ liệu sản phẩm/giỏ hàng/đơn hàng), nhưng **có thể sắp thành mandate từ BTC** (RULES.md nhắc migrate sang managed DB là kịch bản directive điển hình) — **chưa tự làm vội, theo dõi `mandates/` trước khi đầu tư công sức lớn vào đây.**
**Đề xuất:** Để theo dõi, không đưa vào backlog tự làm Tuần 1.

---

## Bổ sung (09/07) — phát hiện mới từ đọc trực tiếp source code từng service

Đợt đọc code sâu (`checkout`, `payment`, `shipping`, `quote`, `currency`, `email`, `accounting/Consumer.cs`, `cart/ValkeyCartStore.cs`) xác nhận thêm các điểm sau, chưa nằm trong backlog gốc.

### R9 — Kafka producer fire-and-forget + `accounting` auto-commit trước khi xử lý xong → có thể mất đơn hàng hoàn toàn âm thầm
**Rủi ro:** Cao — 2 lỗ hổng cộng dồn trên cùng 1 luồng dữ liệu tài chính:
1. `checkout` publish lên Kafka topic `orders` bằng Sarama async producer với `RequiredAcks = sarama.NoResponse` (`kafka/producer.go`) — không chờ xác nhận, có thể rớt message mà `checkout` không hề biết.
2. `accounting` (`Consumer.cs`) dùng `EnableAutoCommit = true` — offset được commit **trước khi** biết `ProcessMessage` có thành công không. Nếu parse lỗi hoặc Postgres đang quá tải, code chỉ log `"Order parsing failed:"` rồi **bỏ luôn message**, không dead-letter, không retry.
**Tác động business:** Rất cao — khách đã bị charge tiền (qua `payment`, xem R4) nhưng đơn hàng có thể **biến mất hoàn toàn khỏi accounting** mà không ai phát hiện, không log ở tầng nào đủ rõ để alert. Nặng hơn R4 vì R4 ít nhất còn giữ lại bằng chứng đơn hàng thất bại; đây là mất dấu vết hoàn toàn.
**Đề xuất:** Đổi `RequiredAcks` sang `WaitForAll` (hoặc `WaitForLocal`) ở `checkout`; đổi `accounting` sang manual commit **sau khi** `SaveChanges()` thành công, thêm dead-letter topic hoặc retry có giới hạn cho message lỗi thay vì drop âm thầm.
**Chi phí:** Thấp — chỉ đổi cấu hình + logic commit, không cần thêm hạ tầng.

### R10 — Thiếu persistence: `valkey-cart` không cấu hình gì, Postgres/Kafka cũng không có PVC
**Rủi ro:** Trung bình (`valkey-cart`) đến Rất cao (Postgres/Kafka) — xác nhận qua `values.yaml` (`valkey-cart` không RDB/AOF/PVC) **và** qua runtime (`kubectl get pv,pvc -A` → không có PV/PVC nào trong toàn cluster). Restart pod (deploy, node drain, OOM...) = mất sạch giỏ hàng đang hoạt động (Valkey), hoặc tệ hơn — mất dữ liệu sản phẩm/review/đơn hàng đã ghi (`accounting`) hoặc dữ liệu đang trong hàng đợi nếu là Postgres/Kafka.
**Tác động business:** Trung bình-cao cho Valkey (khách thêm lại giỏ được, không mất doanh thu trực tiếp, nhưng cộng dồn với R1 vì `valkey-cart` cũng chỉ 1 replica). **Rất cao nếu xảy ra ở Postgres/Kafka** (mất dữ liệu vĩnh viễn) — nhưng đây có thể là phạm vi của mandate migrate-sang-managed-DB sắp tới từ BTC, trùng với R8.
**Đề xuất:** Làm `valkey-cart` trước (bật AOF/RDB + PVC, chi phí thấp, ít rủi ro, cân nhắc cùng lúc R1). Với Postgres/Kafka — **ghi rõ đây là accepted risk có ý thức** trong ADR, không tự ý thêm PVC lớn ngay nếu nghi sắp có mandate managed-DB (tránh làm 2 lần, phí công nếu mandate đến ngay sau).
**Chi phí:** Thấp cho Valkey; trung bình-cao cho Postgres/Kafka nếu tự làm PVC.

### R11 — `currency`: mã tiền tệ không hợp lệ → chia cho 0 → NaN/Inf âm thầm, không có validate input
**Rủi ro:** Thấp khả năng (cần truyền currency code sai/lạ mới trigger) nhưng nghiêm trọng nếu xảy ra: `unordered_map::operator[]` trong `server.cpp` trả về `0.0` mặc định cho code không tồn tại thay vì lỗi, khiến phép chia tạo ra `NaN`/`Inf` thay vì trả lỗi rõ ràng.
**Tác động business:** Trung bình — nếu lọt qua tới bước tính tổng tiền ở `checkout`, khách có thể thấy giá sai (0đ, hoặc số vô nghĩa) thay vì bị chặn lại bằng lỗi dễ debug.
**Đề xuất:** Thêm validate `from_code`/`to_code` nằm trong tập hỗ trợ trước khi tính, trả gRPC `InvalidArgument` nếu không hợp lệ thay vì để tính toán âm thầm sai.
**Chi phí:** Rất thấp — vài dòng validate trong `Convert()`.

### R12 — `quote`: thiếu `numberOfItems` trong request → nuốt exception, trả `0.0` thay vì lỗi
**Rủi ro:** Thấp khả năng, thấp mức nghiêm trọng đơn lẻ, nhưng dễ gây khó hiểu khi debug (không có log lỗi, chỉ thấy phí ship = $0 bất thường).
**Tác động business:** Thấp — nhưng nếu `shipping`/`checkout` có bug gửi thiếu field, phí ship về 0 âm thầm ảnh hưởng trực tiếp doanh thu mà không ai biết để điều tra.
**Đề xuất:** Đổi `quote` trả HTTP 4xx rõ ràng khi thiếu `numberOfItems`, để `shipping` (caller) phải xử lý lỗi thay vì nhận `0.0` hợp lệ giả.
**Chi phí:** Rất thấp.

> **Ghi chú AI (không phải backlog Reliability/Cost, nhưng đáng ghi lại để trả lời hội đồng chính xác):** đọc code xác nhận `llm` service hiện là **mock hoàn toàn** — trả lời/tóm tắt từ dữ liệu tĩnh định sẵn (`product-review-summaries.json`), không gọi LLM thật. Việc cắm LLM thật thuộc phạm vi AIO02 (`values-aio-llm.yaml`), không phải việc của CDO02, nhưng nên biết để trả lời đúng nếu bị hỏi ở Pitch/Readout.

---

## Bổ sung (09/07, chiều) — đối chiếu evidence runtime từ phucdo (đọc read-only qua SSM bastion, ~12:10-12:20 ICT)

Đợt kiểm tra runtime độc lập (không `apply`/`patch`/`scale`, chỉ `get`/`describe`/`events`) xác nhận lại nhiều mục sẵn có (R1, R7/C2/C4) và phát hiện thêm các điểm mới dưới đây. Nguồn: `backlog-runtime-2026-07-09.md` + chứng thực lần 2 cùng ngày.

### ✅ Đã verify (09/07, chiều) — R3 xác nhận đúng, không có mâu thuẫn thật
Kiểm tra trực tiếp trên pod live: `payment-8447bf7668-zx4dj` → `readinessProbe`/`livenessProbe` **rỗng hoàn toàn** (đúng như R3 kết luận), và **không có warning event nào cho `payment`** tại thời điểm kiểm tra — cái phucdo ghi nhận trước đó không tái hiện được, có thể từ 1 pod đã bị thay thế.
Ngược lại, `grafana-7779557549-c7tvr` container `grafana` **có readinessProbe thật** (`httpGet /api/health`, `failureThreshold:3`) — đây là probe mặc định từ **subchart Bitnami**, hoàn toàn độc lập với `default.replicas`/template app chính mà R3 đang nói tới. 2 kết luận không hề mâu thuẫn — chỉ là 2 tầng khác nhau (app tự viết vs. subchart quan sát bên thứ 3). **R3 giữ nguyên, không cần sửa.**
**Phát hiện quan trọng hơn từ lần verify này:** Grafana đang **restart thật, ngay lúc kiểm tra** (`BackOff restarting failed container`, `Readiness probe failed: connection refused` — cách đây 4 phút) — R13 không phải chuyện đã qua, đang **active ngay bây giờ**. Nên xử lý R13 sớm hơn dự kiến, có thể ngay trước Pitch nếu muốn demo Grafana ổn định cho hội đồng xem.

### R13 — 🔴 Grafana OOMKilled — ĐANG ACTIVE, dashboard chính hiện không dùng được (không phải giả định)
**Bằng chứng (mới nhất, verify ~14:50 ICT 09/07):** pod `grafana-7779557549-c7tvr` hiện `CrashLoopBackOff`, `Restart Count: 9` (tăng liên tục trong ngày: 2 → 4 → 9), container chính `Ready: False`. `memory limit: 300Mi` / `request: 250Mi`, cộng thêm 3 sidecar (256Mi mỗi cái) chạy cùng pod. Chu kỳ sống giữa các lần crash đang **ngắn dần** (~3 phút ở lần gần nhất).
**Rủi ro:** Cao, **đang xảy ra thật** — Grafana là công cụ quan sát chính; team hiện không có dashboard dùng được nếu có incident khác xảy ra cùng lúc.
**Tác động business:** Gián tiếp nhưng nghiêm trọng — ảnh hưởng tốc độ phát hiện/phản ứng sự cố ở mọi luồng khác, không riêng 1 service.
**Đề xuất:** Tăng memory limit Grafana lên tối thiểu 512Mi request / 1Gi limit trong Helm values (không patch tay runtime, và nhớ tăng **cả limits lẫn requests** — Kubernetes bắt buộc `requests ≤ limits`), rà lại số sidecar/dashboard đang bật, thêm alert riêng cho OOM/restart của chính Grafana.
**Chi phí:** Rất thấp (chỉ đổi số trong values, thêm ~700Mi memory cho 1 pod).

**Cập nhật (09/07, verify lần 3 lúc ~14:50 ICT) — Grafana đang DOWN THẬT ngay lúc kiểm tra, không phải chuyện đã qua:**
```
grafana-7779557549-c7tvr   3/4   CrashLoopBackOff   9 (4m37s ago)   4h8m
```
`Restart Count` đã tăng liên tục qua 3 lần verify trong ngày: 2 → 4 → **9**. Container `grafana` hiện **Ready: False**, state `Waiting: CrashLoopBackOff` — nghĩa là dashboard **không dùng được ngay lúc này**, không phải "đã restart rồi ổn lại". Chu kỳ crash đang ngắn dần (lần gần nhất: start `14:46:24` → OOM `14:49:03`, chỉ sống được **~3 phút**).

**Tương quan với Jaeger — đã xác nhận lặp lại lần 2, không còn là trùng hợp đơn lẻ:**
- Lần 1 (trưa 09/07): Jaeger OOM `14:17:58 ICT` — Grafana OOM cùng khung giờ ~`14:17` — cách nhau ~1 phút.
- Lần 2 (verify lúc 14:50 ICT, vừa kiểm tra): Jaeger crash lần 3 (`Restart Count: 3`, kết thúc chu kỳ trước lúc `14:48:44`) — Grafana OOM lần 9 kết thúc lúc `14:49:03` — **cách nhau chỉ 19 giây**.
- 2 lần trùng khớp thời gian gần-tuyệt-đối giữa 2 service quan sát độc lập (Grafana, Jaeger — khác code, khác limit, khác pod) trong cùng 1 buổi là **bằng chứng đáng cân nhắc cho 1 nguyên nhân chung** (spike tải/trace volume dội vào cả 2 cùng lúc), dù chưa đủ để khẳng định chắc chắn nếu chưa đối chiếu trực tiếp với ingestion rate của `otel-collector`.
- Nghi vấn nguyên nhân (chưa xác nhận): hệ thống đã public qua CloudFront (`infra/cloudfront.tf`, domain thật đã deploy: `cloudfront_domain_name` có giá trị) — có thể traffic/bot từ ngoài tạo thêm tải trace/dashboard mà limit cũ (đặt lúc chỉ có traffic nội bộ từ load-generator) chưa tính tới. **Cần xem `otel-collector`/Jaeger span ingestion rate quanh 2 khung giờ trên trước khi kết luận chắc chắn** — chưa làm được trong lần verify này.
**Đề xuất bổ sung:** đưa `jaeger.resources.limits.memory` (hiện 600Mi) vào cùng đợt review với Grafana ở R13, đo lại dựa trên traffic public thật thay vì giữ nguyên số đặt từ lúc còn nội bộ. Vì Grafana đang down thật — **đây là ví dụ sống chứng minh R15 (thiếu alerting) đang gây hại thật**: không ai biết dashboard chính đang chết nếu không tự tay `kubectl get pods` kiểm tra.

### R14 — `product-catalog` có crash history thật (restart=3, `Error`, không phải suy đoán)
**Bằng chứng:** pod `product-catalog-d769b79c4-j7wp7`, `Restart Count: 3`, `Last Reason: Error`, `Exit Code: 1`, `memory limit: 20Mi`, `GOMEMLIMIT: 16MiB`.
**Rủi ro:** Cao — đây là service nằm thẳng trên đường business chính (danh mục sản phẩm), memory limit 20Mi rất thấp, khớp với nhóm service đã cảnh báo ở R6 nhưng giờ có bằng chứng crash thật, không còn là suy đoán.
**Tác động business:** Cao — cùng service với R5 (thiếu connection pool Postgres); crash lặp lại làm tăng khả năng mất availability đúng lúc tải cao.
**Đề xuất:** Lấy log `--previous` ngay lần crash tiếp theo để xác định nguyên nhân chính xác (nhiều khả năng liên quan memory 20Mi quá thấp, cộng hưởng với R5); tăng memory limit hợp lý dựa trên số liệu thay vì đoán; ưu tiên làm cùng đợt với R6/R7.
**Chi phí:** Rất thấp (đổi số memory limit) + thời gian điều tra log.

### R15 — Không có alerting cho restart/OOM/readiness fail (gap Observability/Operational Excellence)
**Bằng chứng:** Toàn bộ 3 phát hiện trên (Grafana OOM, product-catalog crash, readiness fail) đều bị phát hiện **thủ công** qua `describe`/`events`, không qua alert nào. `kubectl get pdb -A` chỉ thấy PDB cho `coredns` và `opensearch-pdb` — không có PDB nào bảo vệ checkout path.
**Rủi ro:** Cao — team chỉ biết sự cố khi soi tay hoặc khi khách hàng/UI đã lỗi rõ, không có cảnh báo sớm.
**Tác động business:** Cao — ảnh hưởng trực tiếp tốc độ MTTR (mean time to recovery) cho mọi sự cố khác, kể cả sự cố BTC bơm vào qua flagd.
**Đề xuất:** Thêm Grafana alert rule cho: restart count tăng, OOMKilled, readiness probe fail liên tục >N phút, service checkout path unavailable. Có thể tận dụng `grafana/provisioning/alerting/` đã có sẵn structure cho `cart-service-alerting.yml` làm mẫu, nhân rộng ra service khác.
**Chi phí:** Thấp — chỉ cấu hình alert rule trong Grafana, không cần thêm hạ tầng mới.

**Cross-check với công việc hôm nay:** phucdo xác nhận độc lập việc `metrics-server` đang **không** tồn tại trong cluster (`kubectl top nodes` → `Metrics API not available`) — khớp với việc chính CDO02 đã tự cài thử rồi gỡ trong phiên làm việc sáng nay. Không phải phát hiện mới, chỉ là xác nhận chéo trạng thái hiện tại.

---

## COST OPTIMIZATION

### C1 — Không còn cơ chế dọn image cũ trên ECR (lifecycle policy đã bị xoá do sự cố)
**Rủi ro:** Cao khả năng — đang build/push lại nhiều lần trong 3 tuần, không dọn = phình dung lượng lưu trữ liên tục.
**Tác động business:** Thấp-trung bình (ECR storage rẻ, nhưng cộng dồn 3 tuần + nhiều lần CI chạy có thể đáng kể).
**Đề xuất:** Viết lại lifecycle policy **đúng cách lần này** — dùng `tagPrefixList` riêng cho từng service (rút kinh nghiệm từ chính sự cố đã ghi trong `docs/postmortem/0001-...md`), test trên môi trường không ảnh hưởng trước khi áp dụng.
**Chi phí để sửa:** Thấp.

### C2 — 3 node `t3.large` on-demand cố định, chưa có autoscaling thật chạy
**Rủi ro:** Trung bình — IRSA cho Cluster Autoscaler đã chuẩn bị sẵn trong Terraform nhưng **chưa cài đặt chart thật**, nên hiện tại trả tiền 3 node 24/7 bất kể tải cao/thấp.
**Tác động business:** Trực tiếp vào ngân sách $300/tuần — ước tính ~$42/tuần cho node cố định dù tải ban đêm gần như bằng 0.
**Đề xuất:** Cài `cluster-autoscaler` Helm chart dùng IRSA role đã có sẵn (`cluster_autoscaler_role_arn` output từ Terraform), cấu hình scale-down khi tải thấp.
**Chi phí để sửa:** Thấp (hạ tầng đã chuẩn bị sẵn, chỉ cần `helm install`) — nhưng **phụ thuộc R7** (cần CPU requests để autoscaler tính toán đúng).

### C3 — Chưa dùng Spot instance cho bất kỳ workload nào
**Rủi ro/Tác động:** Tiềm năng tiết kiệm ~60-70% chi phí node cho phần tải chịu được gián đoạn (VD `load-generator`, `recommendation`, `ad` — không quan trọng bằng nhóm checkout).
**Đề xuất:** **Chỉ làm sau khi R1 xong** (tăng replicas) — dùng Spot khi còn `replicas:1` sẽ khuếch đại đúng rủi ro Reliability đang cố sửa. Thứ tự đúng: R1 → C3.
**Chi phí để sửa:** Trung bình (cần thêm node group riêng cho spot, tách theo nhãn workload).

### C4 — Không có CPU limits → không thể right-size chính xác
**Rủi ro:** Trung bình — đang chọn `t3.large` x3 dựa trên ước tính thô, không có số liệu CPU thật để biết đang thừa hay thiếu.
**Tác động business:** Có thể đang trả tiền cho công suất không dùng tới, hoặc ngược lại đang thiếu mà không biết.
**Đề xuất:** Sau khi có R7 (CPU requests/limits) + chạy vài ngày thực tế, xem lại `node_instance_type`/số node trong Terraform — có thể giảm xuống `t3.medium` nếu dư thừa, hoặc xác nhận `t3.large` là đúng.
**Chi phí để sửa:** Thấp (chỉ đổi biến Terraform), nhưng cần dữ liệu trước (phụ thuộc R7).

### C5 — `load-generator` được cấp 1500Mi memory — cao bất thường
**Rủi ro/Tác động:** Thấp-trung bình — đây là bot giả lập traffic, không phục vụ khách thật, nhưng đang chiếm memory limit lớn nhất toàn hệ thống (~17% tổng memory limit cộng dồn).
**Đề xuất:** Xem lại có thực sự cần 1500Mi không, hay đây là giá trị mặc định từ chart gốc chưa tối ưu cho quy mô TF3.
**Chi phí để sửa:** Rất thấp — chỉ cần thử giảm và quan sát.

### C6 — `ResourceQuota` mẫu có sẵn (`deploy/quota.yaml`) chưa được áp dụng
**Cập nhật sau khi xác minh lại:** vì `requests` thực ra đã tồn tại (đính chính ở đầu doc), quota này **có thể áp dụng ngay** mà không làm gãy pod như tôi từng lo ngại — chỉ cần đối chiếu số hiện tại (`requests.memory` cộng dồn ~8.6Gi limit, quota mẫu đặt `requests.memory: 8Gi`) sát nút, cần tăng nhẹ số trong `quota.yaml` hoặc giảm bớt trước khi áp, tránh chặn nhầm việc tăng replicas ở R1.
**Đề xuất:** Điều chỉnh số trong `quota.yaml` cho khớp thực tế sau khi làm xong R1 + R7, rồi mới áp dụng — áp quá sớm sẽ tự chặn chính công việc R1.
**Chi phí để sửa:** Thấp.

### C7 (đã làm, nêu để ghi công) — NAT Gateway đơn (không phải 1/AZ)
Quyết định kiến trúc ban đầu đã chọn 1 NAT Gateway thay vì 3, tiết kiệm ~2/3 chi phí NAT — nêu trong Pitch như bằng chứng đã có tư duy cost-conscious ngay từ lúc dựng baseline, không phải chỉ nói suông.

---

## Thứ tự đề xuất thực thi (không làm hết được, phải chọn)

1. **R13** (Grafana OOMKilled — xác nhận **đang active ngay lúc verify** 09/07 chiều, không phải chuyện đã qua) — đôn lên vị trí #1 vì chi phí rất thấp (đổi số memory), sửa nhanh trước Pitch để demo Grafana ổn định cho hội đồng xem.
2. **R2 + R3** (sửa health check thật + thêm probe — R3 đã verify đúng 09/07 chiều, không mâu thuẫn, giữ nguyên) — nền tảng, chi phí thấp, vá đúng INC-3.
3. **R1** (tăng replicas + PDB nhóm checkout) — tác động business cao nhất, chi phí thấp. Làm cùng lúc: thêm PDB thật (hiện chỉ có PDB cho `coredns`/`opensearch`, chưa có cho checkout path — evidence runtime xác nhận).
4. **R9** (Kafka ack + accounting manual commit) — rủi ro **mất đơn hàng âm thầm hoàn toàn**, nặng hơn R4 về hậu quả, chi phí thấp, xếp ngang hàng R5.
5. **R14** (product-catalog crash history — restart=3 thật) — ưu tiên cao vì đã có bằng chứng crash thật, không còn là suy đoán như R6; làm cùng đợt với R5/R7 vì cùng service.
6. **R5** (connection pool) — vá đúng INC-1, chi phí thấp.
7. **R4** (rollback checkout) — rủi ro tài chính trực tiếp, chi phí thấp.
8. **R7** (CPU requests/limits) — nền tảng bắt buộc cho C2/C4.
9. **C1** (sửa lại lifecycle policy đúng cách) — dọn nợ tự gây ra.
10. **C2** (Cluster Autoscaler thật) — tiết kiệm chi phí đo được ngay.
11. **R15** (alerting restart/OOM/readiness) — chi phí thấp, tận dụng structure alerting có sẵn (`cart-service-alerting.yml` làm mẫu); nên làm sau khi R1/R13/R14 ổn định để alert có ý nghĩa (tránh alert nhiễu lúc hệ thống chưa vá).
12. **C6** (áp ResourceQuota) — làm sau R1+R7.
13. **C3** (Spot) — chỉ sau khi R1 xong.
14. **R10** (Valkey persistence — đã mở rộng phạm vi, xem bản cập nhật 09/07) — làm cùng đợt với R1. Phần Postgres/Kafka trong R10 mở rộng: **ghi accepted risk**, không tự làm PVC lớn nếu nghi sắp có mandate managed-DB.
15. **R6, C4, C5, R11, R12** — làm khi còn thời gian, giá trị/mức nghiêm trọng thấp hơn nhóm trên (R11/R12 chỉ vài dòng code, có thể tranh thủ chèn vào bất kỳ ngày nào rảnh tay).

**Cố ý bỏ ở Tuần 1:** R8 (migrate datastore, kể cả phần Postgres/Kafka mở rộng trong R10) — chờ xem có thành mandate BTC không trước khi tự đầu tư công sức lớn.
