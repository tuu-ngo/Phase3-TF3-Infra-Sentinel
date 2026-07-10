# Backlog ưu tiên — CDO02 (Reliability + Cost Optimization)

**Ngày lập:** 08/07/2026 · **Cập nhật format:** 09/07/2026 (tối)
**Người lập:** arthur (CDO02)
**Trụ phụ trách:** Reliability, Cost Optimization (đã chốt draft với CDO01 — CDO01 giữ Performance Efficiency + Security)
**Công thức xếp hạng:** Ưu tiên = Rủi ro (khả năng × mức nghiêm trọng) × Tác động business (theo `onboarding/SLO.md`, `onboarding/BUDGET.md`, `onboarding/INCIDENT_HISTORY.md`)
**Mã mục:** `REL-XX` = Reliability, `COST-XX` = Cost Optimization.

---

## Đính chính kỹ thuật (ảnh hưởng độ ưu tiên, đọc trước khi vào từng mục)

Lúc đọc code tĩnh (`techx-corp-chart/values.yaml`), từng kết luận "không có `requests`, chỉ có `limits`". Kiểm tra lại trên pod thật cho thấy **kết luận đó sai một phần**: Helm chart tự động mirror `requests = limits` cho memory khi build pod spec — mọi pod hiện có QoS `Guaranteed` cho memory. Cái thật sự thiếu là **CPU**: 28/32 container hoàn toàn không có `requests`/`limits` CPU nào (xem REL-07). Toàn bộ mục dưới đây dựa trên số liệu đã xác minh lại, không phải suy đoán ban đầu.

---

## Đối chiếu với Meeting note liên team (09/06, AI + CDO01 + CDO02)

Cuộc họp chốt backlog chung cho cả 3 team (`P01`-`P25`), phân công owner rõ ràng theo từng mục. Bảng dưới map mã nội bộ CDO02 (`REL-XX`/`COST-XX`) sang mã chung (`P-XX`) và **cập nhật lại Owner** theo đúng phân công đã chốt — thay cho "Chưa gán" ở từng mục bên dưới.

**Nguyên tắc chung (áp dụng từ meeting, đã có sẵn qua các trường Evidence/Ảnh hưởng khách hàng/Rủi ro/Tác động business/Chi phí ở từng mục):** mỗi backlog phải trả lời được (1) ảnh hưởng khách hàng, (2) có gây mất đơn/sai đơn/checkout fail/downtime không, (3) chi phí sửa có hợp lý không, (4) có giúp dễ scale/vận hành/an toàn hơn không, và **(5) AI có thể detect/verify lỗi này thế nào** — câu hỏi thứ 5 là mới, bổ sung riêng cho từng mục P0 ở bảng dưới vì team AI Ops sẽ dùng chính các backlog này làm nguồn cho luồng `raw data → normalize → detect → response → safe check → action suggestion`.

| Mã chung | Mã CDO02 | Nội dung | Owner (đã chốt) | Ưu tiên |
|---|---|---|---|---|
| P01 | REL-02 | Sửa health check giả | **CDO02** (solo) | P0 |
| P02 | REL-03 | Thêm readiness/liveness probe | **CDO01 + CDO02** | P0 |
| P03 | REL-01 | Tăng replicas nhóm checkout | **CDO01 + CDO02** | P0 |
| P04 | REL-04 | Rollback checkout khi ship lỗi sau charge | **CDO02** (solo) | P0 |
| P05 | REL-09 (phần accounting) | Sửa accounting auto-commit quá sớm | **CDO02** (solo) | P0 |
| P06 | REL-09 (phần Kafka) | Kafka ack/retry/manual-commit/DLQ | **CDO02** (solo) | P0 |
| P07 | *(mới — xem dưới)* | Cài lại metrics-server | **CDO01** (solo) — không còn là việc CDO02 tự làm | P0 |
| P08 | REL-06 (mở rộng) | Baseline load test + RED metrics browse/cart/checkout | **CDO01** (solo, CDO02 hỗ trợ số liệu) | P0 |
| P09 | REL-13 | Grafana/Jaeger OOM/restart | **CDO01 + CDO02** | P0 |
| P10 | REL-15 | Alert cho OOMKilled/restart/readiness fail | **CDO01 + CDO02** | P0 |
| P11 | *(mới)* | HPA cho service quan trọng | **CDO01** (solo) | P1 |
| P12 | REL-07 | CPU requests/limits còn thiếu | **CDO01** (solo) — meeting chuyển hẳn khỏi CDO02 | P1 |
| P13 | REL-05 | Connection pool Postgres | **CDO02** (solo) | P1 |
| P14 | REL-10 (phần Valkey) | Valkey cart persistence | **CDO02** (solo) | P1 |
| P15 | *(mới — xem dưới)* | NetworkPolicy chặn lateral movement | **CDO01** (solo) | P0 |
| P16 | *(mới — xem dưới)* | Chốt public ingress boundary (CloudFront-only vs ALB public) | **CDO01** (solo) — **liên quan trực tiếp `infra/cloudfront.tf` CDO02 vừa dựng** | P0 |
| P18 | COST-06 | ResourceQuota + LimitRange | **CDO01** (solo) — meeting chuyển khỏi CDO02 | P1 |
| P22 | COST-02 | Cluster Autoscaler/Karpenter + ADR | **CDO01** (solo) — meeting chuyển khỏi CDO02 | — |
| — | REL-08, REL-10 (phần Postgres/Kafka), REL-11, REL-12, COST-01, COST-03, COST-04, COST-05, COST-07 | Không có mã P tương ứng | **CDO02** giữ nguyên, ngoài phạm vi họp chung | — |

**Điểm quan trọng cần nêu rõ trong Pitch:** 3 mục CDO02 từng để "Owner: Chưa gán" (REL-07/P12, COST-02/P22, COST-06/P18) **đã được meeting chuyển hẳn sang CDO01** — không phải CDO02 bỏ sót, mà là phân công lại có chủ đích theo đúng trụ (CDO01 giữ Performance Efficiency + Security, các mục này thiên về performance-tuning/cost-infra hơn Reliability thuần). CDO02 không cần ôm các mục này trong Pitch của mình nữa, chỉ nêu đã tìm ra + đã bàn giao.

### P07 — Cài lại metrics-server (mới, CDO01 sở hữu)
Đã từng được CDO02 tự cài (09/07 sáng, xác nhận qua audit log) rồi biến mất khỏi cluster cùng ngày (nguyên nhân chưa rõ — không liên quan tới đợt rolling-replace node). Meeting chốt CDO01 cài lại và duy trì — vì đây là hạ tầng observability nền tảng phục vụ cả P08 (RED metrics), P11 (HPA), P12 (CPU sizing), không riêng gì Reliability.

### P08 — Baseline load test + RED metrics cho browse/cart/checkout (mở rộng từ REL-06, CDO01 sở hữu)
REL-06 ban đầu chỉ scope hẹp (tìm memory limit đúng qua load test). Meeting mở rộng thành baseline RED (Rate/Error/Duration) chính thức cho 3 luồng SLO chính — CDO01 chủ trì vì thuộc mảng Performance Efficiency, CDO02 cung cấp bằng chứng runtime đã có (evidence OOM, crash history) làm input.

### P15 — NetworkPolicy chặn lateral movement tới Postgres/Valkey/Grafana (mới, CDO01 sở hữu, P0)
Hiện **không có NetworkPolicy nào** trong cluster — bất kỳ pod nào cũng gọi thẳng được tới Postgres/Valkey/Grafana nếu biết Service DNS, không có rào chắn network-level. CDO01 sở hữu (thuộc trụ Security), nhưng CDO02 cần biết vì đụng chung datastore đang theo dõi ở REL-08/REL-10.

### P16 — Chốt public ingress boundary: CloudFront-only hay ALB public HTTP (mới, CDO01 sở hữu, P0 — **liên quan trực tiếp việc CDO02 vừa làm**)
CDO02 vừa dựng xong CloudFront (`infra/cloudfront.tf`) trước ALB — nhưng **ALB hiện vẫn nhận trực tiếp traffic public HTTP**, không giới hạn chỉ nhận từ CloudFront. Nghĩa là ai biết được DNS name của ALB (`k8s-techxtf3-frontend-...elb.amazonaws.com`) có thể **bỏ qua CloudFront hoàn toàn** (né cache, né mọi kiểm soát ở tầng CloudFront nếu sau này thêm WAF). Đây chính là câu hỏi P16 đang đặt ra — **quyết định chưa chốt**, cần CDO01 (Security) quyết + có thể cần CDO02 sửa lại `infra/cloudfront.tf`/security group ALB để enforce (VD `alb.ingress.kubernetes.io/inbound-cidrs` giới hạn theo CloudFront managed prefix list, hoặc custom header secret CloudFront→ALB). **Nêu chủ động trong Pitch — đừng để mentor hỏi trước.**

---

## RELIABILITY

## REL-01 — Tăng replicas ≥2 cho nhóm checkout + thêm PodDisruptionBudget
*Trụ:* Reliability · *Ưu tiên đề xuất:* P0 · *Owner:* Chưa gán — cần chốt trong họp CDO01/CDO02

- *Evidence:*
  `techx-corp-chart/values.yaml`: `default.replicas: 1` áp dụng toàn bộ ~18 app component, không override cho `cart`/`checkout`/`payment`/`currency`/`product-catalog`/`shipping`. Xác nhận lại trên runtime (evidence chéo từ phucdo, 09/07): `kubectl -n techx-tf3 get deploy` — toàn bộ deployment app đang `DESIRED=1`/`AVAILABLE=1`. `kubectl get pdb -A` chỉ thấy PDB cho `coredns` và `opensearch-pdb` — **không có PDB nào bảo vệ checkout path**.
- *Ảnh hưởng khách hàng:*
  1 pod chết (crash, node drain, OOM) = mất hoàn toàn 1 chặng trong luồng mua hàng trong lúc pod restart (vài giây tới vài chục giây tùy readiness). Khách đang ở giữa flow checkout gặp lỗi 5xx hoặc timeout.
- *Rủi ro (khả năng × mức nghiêm trọng):*
  Khả năng cao (đã từng xảy ra thật ở INC-2) × nghiêm trọng cao (đụng thẳng luồng ra tiền) = **P0**.
- *Tác động business (SLO/BUDGET/INCIDENT_HISTORY):*
  Checkout SLO ≥99% (`SLO.md`) — mất 1 pod trong nhóm checkout trực tiếp đe dọa ngưỡng này. INC-2 đã xảy ra thật vì đúng nguyên nhân này (xem `INCIDENT_HISTORY.md`).
- *Giải pháp đề xuất:*
  Set `replicas: 2` cho `cart`, `checkout`, `payment`, `currency`, `product-catalog`, `shipping` trong values override; thêm `PodDisruptionBudget` (`minAvailable: 1`) cho từng service này; cân nhắc `topologySpreadConstraints` để tránh 2 pod cùng node.
- *Chi phí / effort:*
  ~2-3 giờ-người (sửa values + test). Chi phí hạ tầng: nhân đôi ~6 pod nhỏ, tổng thêm vài trăm Mi memory — không đáng kể so với trần $300/tuần.
- *Acceptance criteria:*
  `kubectl get deploy` cho 6 service trên hiển thị `AVAILABLE=2`; PDB tồn tại và `ALLOWED DISRUPTIONS ≥1`; kill thủ công 1 pod trong nhóm, xác nhận request checkout vẫn thành công (không có lỗi 5xx quan sát được trong lúc pod đang restart).
- *Rollback / nếu làm sai:*
  `helm upgrade --install techx-corp ... --set <service>.replicas=1` để trả lại giá trị cũ (kèm lại `-f values-flagd-sync.yaml`, bắt buộc theo GETTING_STARTED.md). Nếu replicas mới gây thiếu tài nguyên node (Pending), phát hiện ngay qua `kubectl get pods` (vài phút) do pod không schedule được.

## REL-02 — Sửa health check giả thành kiểm tra dependency thật
*Trụ:* Reliability · *Ưu tiên đề xuất:* P0 · *Owner:* Chưa gán

- *Evidence:*
  Đọc code xác nhận `checkout`, `product-catalog`, `recommendation`, `currency`, `product-reviews`, `ad`, `payment` đều có handler gRPC health check trả `SERVING` cố định, không gọi thử dependency thật (DB/Kafka/Redis). *(Cần bổ sung số dòng file chính xác cho từng service trước khi đưa vào slide chính thức — chưa ghi lại lúc đọc code lần đầu.)*
- *Ảnh hưởng khách hàng:*
  Khách vẫn được route request tới pod dù dependency (Postgres/Kafka/Redis) của pod đó đã chết — nhận lỗi 5xx thay vì được K8s tự động loại pod hỏng khỏi endpoint.
- *Rủi ro (khả năng × mức nghiêm trọng):*
  Khả năng cao (health check giả đang tồn tại ở gần như toàn bộ service) × nghiêm trọng cao (làm vô hiệu hóa toàn bộ giá trị của REL-03) = **P0**.
- *Tác động business (SLO/BUDGET/INCIDENT_HISTORY):*
  Tiền đề bắt buộc để REL-03 (thêm probe) có tác dụng thật — nếu không sửa mục này trước, thêm probe ở REL-03 chỉ là hình thức, K8s vẫn nghĩ pod khỏe.
- *Giải pháp đề xuất:*
  Sửa hàm `Check()`/health handler ở từng service: gọi `db.Ping()` (Postgres), kiểm tra kết nối Kafka/Redis trước khi trả `SERVING`; trả `NOT_SERVING` nếu dependency không phản hồi trong timeout ngắn.
- *Chi phí / effort:*
  Thấp — ~30-60 phút/service × 7 service, chỉ sửa logic, không cần hạ tầng mới.
- *Acceptance criteria:*
  Tắt thủ công dependency của 1 service (VD chặn Postgres của `product-catalog` bằng NetworkPolicy tạm) → health check của service đó phải chuyển `NOT_SERVING` trong ≤ 1 chu kỳ probe.
- *Rollback / nếu làm sai:*
  Revert commit sửa logic `Check()` qua `git revert`, redeploy image cũ. Nếu health check mới quá nhạy (false positive NOT_SERVING làm rớt traffic oan), phát hiện qua tăng đột biến lỗi 5xx trên Grafana `apm-dashboard` — thời gian phát hiện phụ thuộc REL-15 (hiện chưa có alert, phải soi tay).

## REL-03 — Thêm readinessProbe/livenessProbe cho toàn bộ service (ưu tiên nhóm checkout)
*Trụ:* Reliability · *Ưu tiên đề xuất:* P0 · *Owner:* Chưa gán

- *Evidence:*
  `techx-corp-chart/values.yaml` không có key `readinessProbe`/`livenessProbe` nào cho app component. Verify trực tiếp trên pod live (09/07): `kubectl -n techx-tf3 get pod payment-8447bf7668-zx4dj -o jsonpath='{.spec.containers[0].readinessProbe}'` → **rỗng hoàn toàn**, không có warning event nào cho `payment` tại thời điểm kiểm tra. (Đối chứng: Grafana có probe riêng nhưng đến từ subchart Bitnami, không liên quan app components — không mâu thuẫn với kết luận này.)
- *Ảnh hưởng khách hàng:*
  Mỗi lần deploy/rollout, K8s route traffic vào pod mới trước khi pod thật sự sẵn sàng nhận request → khách gặp lỗi ngay lúc deploy (đúng kịch bản đã xảy ra ở INC-3, lỗi thanh toán lúc deploy).
- *Rủi ro (khả năng × mức nghiêm trọng):*
  Khả năng cao (xảy ra ở **mọi lần** rollout) × nghiêm trọng cao (đã gây lỗi thanh toán thật) = **P0**.
- *Tác động business (SLO/BUDGET/INCIDENT_HISTORY):*
  Nguyên nhân gốc xác nhận của INC-3, **vẫn chưa được vá tới giờ**. Mỗi lần deploy/rollout trong 3 tuần còn lại có nguy cơ tái diễn.
- *Giải pháp đề xuất:*
  Thêm `readinessProbe`/`livenessProbe` (gRPC health check hoặc HTTP `/healthz` tùy service) vào template pod cho toàn bộ component, ưu tiên nhóm checkout trước. **Phụ thuộc REL-02** — probe vô nghĩa nếu health check backend vẫn giả.
- *Chi phí / effort:*
  Thấp — chủ yếu cấu hình YAML, ~2-3 giờ-người cho toàn bộ chart.
- *Acceptance criteria:*
  `kubectl rollout restart deploy/checkout` (và tương tự cho nhóm checkout) không gây lỗi 5xx quan sát được phía client trong suốt quá trình rollout (test bằng cách gọi liên tục vào storefront lúc rollout).
- *Rollback / nếu làm sai:*
  `helm rollback techx-corp <revision trước>`. Nếu probe threshold sai làm pod bị đánh rớt liên tục dù healthy thật (false CrashLoopBackOff), phát hiện trong vài phút qua `kubectl get pods` (READY giảm bất thường).

## REL-04 — Thêm logic rollback/refund cho `checkout.PlaceOrder` khi ship lỗi sau khi đã charge
*Trụ:* Reliability · *Ưu tiên đề xuất:* P0 · *Owner:* Chưa gán

- *Evidence:*
  `checkout/main.go` (~dòng 329-345), xác nhận trực tiếp qua đọc code:
  ```go
  txID, err := cs.chargeCard(ctx, total, req.CreditCard)
  if err != nil {
      return nil, status.Errorf(codes.Internal, "failed to charge card: %+v", err)
  }
  ...
  shippingTrackingID, err := cs.shipOrder(ctx, req.Address, prep.cartItems)
  if err != nil {
      return nil, status.Errorf(codes.Unavailable, "shipping error: %+v", err)
  }
  ```
  Không có bất kỳ logic hoàn tiền/void payment nào trong toàn bộ codebase khi nhánh lỗi thứ 2 xảy ra.
- *Ảnh hưởng khách hàng:*
  Khách bị trừ tiền thật nhưng đơn hàng thất bại — không có cơ chế hoàn tiền tự động, khách phải tự khiếu nại.
- *Rủi ro (khả năng × mức nghiêm trọng):*
  Khả năng trung bình (cần đúng lúc `shipOrder` lỗi sau khi `chargeCard` đã thành công) × nghiêm trọng rất cao (mất tiền thật của khách, ảnh hưởng uy tín) = **P0** (ưu tiên theo mức nghiêm trọng, không phải tần suất).
- *Tác động business (SLO/BUDGET/INCIDENT_HISTORY):*
  Ảnh hưởng trực tiếp uy tín + khiếu nại tài chính thật — không có SLO nào "che" được rủi ro này vì nó không phải lỗi tỉ lệ mà là lỗi tài chính từng vụ việc.
- *Giải pháp đề xuất:*
  Thêm logic bù trừ (gọi `Payment.Void`/refund) khi `shipOrder` lỗi sau `chargeCard` thành công; hoặc đảo thứ tự gọi (ship trước, charge sau) nếu nghiệp vụ cho phép — cần bàn với PM trước khi đổi thứ tự vì ảnh hưởng flow nghiệp vụ.
- *Chi phí / effort:*
  Thấp — chỉ sửa logic Go trong `checkout/main.go`, ~2-4 giờ-người kể cả viết test.
- *Acceptance criteria:*
  Test giả lập `shipOrder` lỗi (VD tắt tạm `shipping` service) sau khi charge thành công → xác nhận có request refund/void được gửi tới `payment`, log rõ ràng để trace được giao dịch.
- *Rollback / nếu làm sai:*
  `git revert` commit, redeploy image `checkout` cũ. Nếu logic refund tự động sai (refund nhầm đơn thành công), phát hiện qua đối chiếu số liệu `accounting` vs `payment` — hiện chưa có alert tự động (phụ thuộc REL-15), cần soi tay, có thể mất vài giờ tới khi ai đó kiểm tra sổ sách.

## REL-05 — Thêm connection pool Postgres cho `product-catalog` và `product-reviews`
*Trụ:* Reliability · *Ưu tiên đề xuất:* P1 · *Owner:* Chưa gán

- *Evidence:*
  `product-catalog/main.go` (~dòng 138-167), hàm `initDatabase()`: mở DB qua `otelsql.Open("postgres", connStr, ...)`, **không có** bất kỳ lệnh gọi `SetMaxOpenConns`/`SetMaxIdleConns`/`SetConnMaxLifetime` nào — dùng default `database/sql` (unlimited open connections). `product-reviews/database.py`: `psycopg2.connect(db_connection_str)` được mở **mới hoàn toàn cho mỗi lần query** (`fetch_product_reviews_from_db`, `fetch_avg_product_review_score_from_db`), trong `with ... finally: connection.close()` — 1 TCP connection mới/request, không pool.
- *Ảnh hưởng khách hàng:*
  Dưới tải cao, connection tới Postgres cạn kiệt → khách không xem được danh mục sản phẩm / review, hoặc tính năng tóm tắt AI (dùng chung Postgres) bị lỗi theo.
- *Rủi ro (khả năng × mức nghiêm trọng):*
  Khả năng cao (nguyên nhân gốc y hệt INC-1, đã có PoC là chính sự cố đã từng xảy ra) × nghiêm trọng cao (đụng cả `product-catalog` lẫn `accounting` dùng chung Postgres) = **P1** (đã biết, chờ REL-01/REL-02/REL-03/REL-09 xong trước vì foundation hơn).
- *Tác động business (SLO/BUDGET/INCIDENT_HISTORY):*
  Vá đúng nguyên nhân gốc của INC-1. `product-reviews` phục vụ tính năng AI chủ lực của sản phẩm (tóm tắt review).
- *Giải pháp đề xuất:*
  `product-catalog`: gọi `SetMaxOpenConns`/`SetMaxIdleConns` với số hợp lý (đo theo `max_connections` của Postgres chia cho số service dùng chung). `product-reviews`: chuyển sang connection pool (`psycopg2.pool.SimpleConnectionPool` hoặc SQLAlchemy engine) thay vì connect-per-request.
- *Chi phí / effort:*
  Thấp — chỉ sửa code, không cần thêm hạ tầng. ~3-4 giờ-người cả 2 service kể cả test tải nhẹ.
- *Acceptance criteria:*
  Load test với `LOCUST_USERS` tăng dần, quan sát `pg_stat_activity` connection count không vượt ngưỡng đặt trước; không có lỗi "too many connections" xuất hiện trong log.
- *Rollback / nếu làm sai:*
  `git revert` + redeploy image cũ. Nếu pool size đặt quá thấp gây nghẽn ngược (request phải chờ connection), phát hiện qua tăng p95 latency trên Grafana `apm-dashboard` — vài phút nếu có người đang theo dõi dashboard, lâu hơn nếu không (phụ thuộc REL-15).

## REL-06 — Load test có kiểm soát để xác định memory limit thật cho các service còn lại
*Trụ:* Reliability · *Ưu tiên đề xuất:* P2 · *Owner:* Chưa gán

- *Evidence:*
  `accounting` đã OOMKilled thật 44 lần/19h (đã vá 120Mi→350Mi, xem `docs/postmortem/0001-...md`). Các service khác có memory limit tương tự thấp: `checkout` 20Mi, `product-catalog` 20Mi, `currency` 20Mi (`values.yaml`) — chưa có bằng chứng crash thật ở nhóm này (khác REL-14, đã có bằng chứng crash thật cho `product-catalog`).
- *Ảnh hưởng khách hàng:*
  Nếu memory limit quá thấp cho service trên đường checkout, khách gặp lỗi 5xx khi service đó bị OOMKill giữa lúc đang phục vụ request.
- *Rủi ro (khả năng × mức nghiêm trọng):*
  Khả năng trung bình (chưa xác nhận crash thật ngoài `product-catalog`) × nghiêm trọng trung bình-cao nếu xảy ra ở service checkout = **P2** (REL-14 đã tách phần `product-catalog` có bằng chứng thật ra ưu tiên cao hơn).
- *Tác động business (SLO/BUDGET/INCIDENT_HISTORY):*
  Trung bình-cao nếu xảy ra ở service trên đường checkout, khác `accounting` vốn không chặn checkout trực tiếp.
- *Giải pháp đề xuất:*
  Load test có kiểm soát (tăng dần `LOCUST_USERS` trên `load-generator`), quan sát memory usage thật qua `kubectl top pods` (cần REL đã cài lại `metrics-server` — hiện chưa có), điều chỉnh limit dựa trên số liệu, không đoán.
- *Chi phí / effort:*
  Trung bình — cần thời gian chạy test có kiểm soát, khoảng nửa ngày làm việc.
- *Acceptance criteria:*
  Có bảng số liệu memory usage thật theo từng mức tải cho mỗi service; memory limit mới được đặt có margin an toàn ≥30% so với đỉnh đo được.
- *Rollback / nếu làm sai:*
  Trả limit về giá trị cũ qua `helm upgrade` với values trước đó. Nếu limit mới vẫn thấp gây OOM tiếp, phát hiện qua `kubectl get pods` restart count tăng — vài phút tới vài giờ tùy có ai theo dõi hay không.

## REL-07 — Thêm CPU requests/limits cho 28/32 container còn thiếu
*Trụ:* Reliability · *Ưu tiên đề xuất:* P1 · *Owner:* Chưa gán

- *Evidence:*
  Xác minh qua `kubectl get pods -o json`: 28/32 container hoàn toàn không có `requests`/`limits` CPU nào. Bằng chứng chéo (phucdo, node describe): `CPU Requests: 0`, `CPU Limits: 0` cho phần lớn workload app.
- *Ảnh hưởng khách hàng:*
  Không có ảnh hưởng khách hàng trực tiếp ngay lập tức — rủi ro âm thầm (noisy neighbor giữa các pod cùng node) có thể gây latency tăng không rõ nguyên nhân.
- *Rủi ro (khả năng × mức nghiêm trọng):*
  Khả năng trung bình (tích lũy theo thời gian, tăng khi thêm replicas ở REL-01) × nghiêm trọng trung bình = **P1** — là nền tảng bắt buộc cho COST-02/COST-04, nên cần làm sớm dù tự thân không cấp bách bằng nhóm P0.
- *Tác động business (SLO/BUDGET/INCIDENT_HISTORY):*
  Chặn khả năng bật HPA theo CPU và Cluster Autoscaler tính toán đúng (COST-02) — gián tiếp ảnh hưởng cả Reliability lẫn Cost.
- *Giải pháp đề xuất:*
  Đo CPU usage thật qua load test nhẹ trước (không đặt bừa số), sau đó thêm `resources.requests.cpu`/`limits.cpu` cho toàn bộ 28 container còn thiếu trong values override.
- *Chi phí / effort:*
  Thấp về effort cấu hình (~2 giờ), nhưng cần thời gian đo trước (phụ thuộc có `metrics-server`/`kubectl top` hoạt động).
- *Acceptance criteria:*
  `kubectl describe pod` cho mọi container hiển thị CPU requests/limits khác 0; `kubectl top pods` (khi có metrics-server) không cho thấy pod nào ăn quá 100% CPU limit liên tục.
- *Rollback / nếu làm sai:*
  `helm upgrade` với values cũ (bỏ CPU limits). Nếu limit đặt quá thấp gây throttling (CPU throttled), phát hiện qua tăng latency bất thường trên Grafana — cần theo dõi thủ công cho tới khi có REL-15.

## REL-08 — Datastore đơn lẻ: Postgres/Valkey/Kafka mỗi loại 1 instance (theo dõi, không chủ động làm)
*Trụ:* Reliability · *Ưu tiên đề xuất:* P2 (theo dõi) · *Owner:* Chưa gán

- *Evidence:*
  `values.yaml`: `postgresql`, `kafka`, `valkey-cart` đều `replicas: 1` (là 3 trong số ít override khác `default.replicas`, nhưng vẫn = 1, không phải HA).
- *Ảnh hưởng khách hàng:*
  Nếu 1 trong 3 datastore chết hoàn toàn (không chỉ pod restart mà node/AZ mất), toàn bộ tính năng phụ thuộc ngừng hoạt động cho tới khi pod được tái tạo — nặng hơn SPOF tầng service vì kèm rủi ro mất dữ liệu (xem REL-10).
- *Rủi ro (khả năng × mức nghiêm trọng):*
  Khả năng thấp (chưa xảy ra sự cố thật) × nghiêm trọng rất cao nếu xảy ra = **P2, nhưng theo dõi sát**, không phải bỏ qua.
- *Tác động business (SLO/BUDGET/INCIDENT_HISTORY):*
  Rất cao nếu xảy ra (mất toàn bộ dữ liệu sản phẩm/giỏ hàng/đơn hàng) — nhưng **có thể sắp thành mandate từ BTC** (`RULES.md` nhắc migrate sang managed DB là kịch bản directive điển hình).
- *Giải pháp đề xuất:*
  **Không tự làm Tuần 1.** Theo dõi `phase3 - information/mandates/` — nếu mandate migrate-managed-DB xuất hiện, việc này tự động được ưu tiên lại theo yêu cầu BTC.
- *Chi phí / effort:*
  Không áp dụng — chưa hành động, chỉ theo dõi.
- *Acceptance criteria:*
  Không áp dụng cho tuần này; tiêu chí done sẽ định nghĩa lại nếu mandate xuất hiện.
- *Rollback / nếu làm sai:*
  Không áp dụng — chưa có hành động để rollback.

## REL-09 — Đổi Kafka producer/consumer để tránh mất đơn hàng âm thầm
*Trụ:* Reliability · *Ưu tiên đề xuất:* P0 · *Owner:* Chưa gán

- *Evidence:*
  `checkout/kafka/producer.go`: publish lên topic `orders` bằng Sarama async producer với `RequiredAcks = sarama.NoResponse` — fire-and-forget, không chờ xác nhận. `accounting/Consumer.cs`: `EnableAutoCommit = true` — offset commit **trước khi** biết `ProcessMessage` thành công hay không; nếu parse lỗi hoặc Postgres quá tải, code chỉ log `"Order parsing failed:"` rồi bỏ luôn message, không dead-letter, không retry.
- *Ảnh hưởng khách hàng:*
  Khách đã bị trừ tiền (qua `payment`) nhưng đơn hàng có thể **biến mất hoàn toàn khỏi hệ thống accounting** — khách không nhận được hàng, không có cách nào tra cứu vì không còn dấu vết trong DB.
- *Rủi ro (khả năng × mức nghiêm trọng):*
  Khả năng trung bình (cần Kafka/Postgres gặp vấn đề đúng lúc xử lý message) × nghiêm trọng rất cao (mất dữ liệu tài chính hoàn toàn, không phải chỉ thiếu rollback như REL-04) = **P0**.
- *Tác động business (SLO/BUDGET/INCIDENT_HISTORY):*
  Nặng hơn REL-04 vì REL-04 ít nhất còn giữ lại bằng chứng đơn hàng thất bại (lỗi trả về ngay); đây là mất dấu vết hoàn toàn, không log ở tầng nào đủ rõ để alert.
- *Giải pháp đề xuất:*
  Đổi `RequiredAcks` sang `WaitForAll` (hoặc tối thiểu `WaitForLocal`) ở `checkout`; đổi `accounting` sang manual commit **sau khi** `SaveChanges()` thành công; thêm dead-letter topic hoặc retry có giới hạn cho message lỗi thay vì drop âm thầm.
- *Chi phí / effort:*
  Thấp — chỉ đổi cấu hình + logic commit, không cần thêm hạ tầng. ~3-4 giờ-người kể cả test.
- *Acceptance criteria:*
  Test giả lập Postgres tạm ngưng lúc `accounting` đang xử lý message → message phải được retry/dead-letter, không bị mất; offset chỉ commit sau khi `SaveChanges()` xác nhận thành công.
- *Rollback / nếu làm sai:*
  `git revert` + redeploy `checkout`/`accounting`. Nếu `WaitForAll` làm chậm checkout đáng kể (do chờ ack), phát hiện qua tăng p95 latency checkout trên Grafana — cần theo dõi chủ động vì chưa có alert tự động (REL-15).

## REL-10 — Bật persistence cho `valkey-cart`; ghi nhận accepted risk cho Postgres/Kafka
*Trụ:* Reliability · *Ưu tiên đề xuất:* P1 · *Owner:* Chưa gán

- *Evidence:*
  `values.yaml` (`valkey-cart`): không RDB, không AOF, không PVC. Runtime: `kubectl get pv,pvc -A` → **không có PV/PVC nào trong toàn cluster** — nghĩa là Postgres và Kafka cũng hoàn toàn không có persistent storage, không riêng Valkey.
- *Ảnh hưởng khách hàng:*
  Restart pod `valkey-cart` (deploy, node drain, OOM) = khách đang có giỏ hàng mất sạch, phải thêm lại từ đầu. Nếu là Postgres/Kafka: mất dữ liệu sản phẩm/review/đơn hàng đã ghi vĩnh viễn.
- *Rủi ro (khả năng × mức nghiêm trọng):*
  Valkey: khả năng trung bình (cộng dồn với REL-01, `valkey-cart` cũng 1 replica) × nghiêm trọng trung bình = P1. Postgres/Kafka: nghiêm trọng rất cao nhưng trùng phạm vi REL-08 (chờ mandate) → giữ ở mức theo dõi/accepted risk, không tách P0.
- *Tác động business (SLO/BUDGET/INCIDENT_HISTORY):*
  Valkey: không mất doanh thu trực tiếp (khách thêm lại giỏ được) nhưng ảnh hưởng trải nghiệm mỗi lần deploy. Postgres/Kafka: rất cao nếu xảy ra, nhưng có thể trùng phạm vi mandate managed-DB sắp tới.
- *Giải pháp đề xuất:*
  Bật AOF (`appendonly yes`) hoặc RDB snapshot định kỳ + PVC cho `valkey-cart`, làm cùng đợt với REL-01. Với Postgres/Kafka: **ghi rõ đây là accepted risk có ý thức** trong ADR, không tự ý thêm PVC lớn ngay nếu nghi sắp có mandate managed-DB.
- *Chi phí / effort:*
  Thấp cho Valkey (~1-2 giờ-người). Không áp dụng cho Postgres/Kafka tuần này (accepted risk).
- *Acceptance criteria:*
  Restart thủ công pod `valkey-cart` → xác nhận giỏ hàng test không bị mất sau khi pod lên lại. ADR ghi rõ accepted risk cho Postgres/Kafka được review và ký bởi CDO02.
- *Rollback / nếu làm sai:*
  `helm upgrade` bỏ cấu hình persistence nếu gây lỗi khởi động Valkey. Phát hiện qua `kubectl get pods` (Valkey CrashLoopBackOff) trong vài phút.

## REL-11 — Validate currency code trước khi tính, tránh chia cho 0 âm thầm
*Trụ:* Reliability · *Ưu tiên đề xuất:* P2 · *Owner:* Chưa gán

- *Evidence:*
  `currency/server.cpp`: `unordered_map::operator[]` trả về `0.0` mặc định cho currency code không tồn tại thay vì lỗi, khiến phép chia tạo ra `NaN`/`Inf` thay vì trả lỗi rõ ràng. Không có validate `from_code`/`to_code` trước khi tính.
- *Ảnh hưởng khách hàng:*
  Nếu lọt qua tới bước tính tổng tiền ở `checkout`, khách có thể thấy giá sai (0đ hoặc số vô nghĩa) thay vì bị chặn lại bằng lỗi dễ hiểu.
- *Rủi ro (khả năng × mức nghiêm trọng):*
  Khả năng thấp (cần truyền currency code sai/lạ mới trigger) × nghiêm trọng trung bình = **P2**.
- *Tác động business (SLO/BUDGET/INCIDENT_HISTORY):*
  Không map trực tiếp tới SLO/incident nào đã biết — rủi ro tiềm ẩn về tính đúng đắn dữ liệu giá.
- *Giải pháp đề xuất:*
  Thêm validate `from_code`/`to_code` nằm trong tập hỗ trợ trước khi tính, trả gRPC `InvalidArgument` nếu không hợp lệ.
- *Chi phí / effort:*
  Rất thấp — vài dòng validate trong `Convert()`, ~30 phút.
- *Acceptance criteria:*
  Gọi `Convert()` với currency code không tồn tại → nhận `InvalidArgument`, không nhận `NaN`/`Inf`.
- *Rollback / nếu làm sai:*
  `git revert`, redeploy `currency`. Rủi ro thấp vì thay đổi nhỏ, phát hiện ngay qua unit test nếu có.

## REL-12 — `quote` trả lỗi rõ ràng khi thiếu field thay vì nuốt exception
*Trụ:* Reliability · *Ưu tiên đề xuất:* P2 · *Owner:* Chưa gán

- *Evidence:*
  `quote/app/routes.php`, `calculateQuote()`: nếu thiếu `numberOfItems` trong body, `InvalidArgumentException` bị catch và **nuốt lặng lẽ**, trả về `0.0` thay vì lỗi HTTP.
- *Ảnh hưởng khách hàng:*
  Nếu `shipping`/`checkout` có bug gửi thiếu field, khách có thể thấy phí ship = $0 âm thầm — lợi khách nhưng thiệt doanh thu, và không ai biết để điều tra.
- *Rủi ro (khả năng × mức nghiêm trọng):*
  Khả năng thấp × nghiêm trọng thấp đơn lẻ, nhưng dễ gây khó hiểu khi debug = **P2**.
- *Tác động business (SLO/BUDGET/INCIDENT_HISTORY):*
  Thấp trực tiếp, nhưng ảnh hưởng doanh thu âm thầm nếu bug thật sự xảy ra ở caller.
- *Giải pháp đề xuất:*
  Đổi `quote` trả HTTP 4xx rõ ràng khi thiếu `numberOfItems`, để `shipping` (caller) phải xử lý lỗi thay vì nhận `0.0` hợp lệ giả.
- *Chi phí / effort:*
  Rất thấp — ~20-30 phút.
- *Acceptance criteria:*
  Gọi `/getquote` thiếu `numberOfItems` → nhận HTTP 4xx với message rõ ràng, không nhận `200` kèm `0.0`.
- *Rollback / nếu làm sai:*
  `git revert`, redeploy `quote`. Rủi ro thấp.

## REL-13 — 🔴 Grafana OOMKilled — ĐANG ACTIVE, dashboard chính hiện không dùng được
*Trụ:* Reliability / Observability · *Ưu tiên đề xuất:* P0 · *Owner:* Chưa gán

- *Evidence:*
  Verify trực tiếp lúc ~14:50 ICT 09/07: `grafana-7779557549-c7tvr` đang `CrashLoopBackOff`, `Restart Count: 9` (tăng liên tục trong ngày: 2 → 4 → 9 qua 3 lần kiểm tra), container chính `Ready: False`, `Last State: OOMKilled`, `Exit Code: 137`. `memory limit: 300Mi` / `request: 250Mi` — không đổi từ lúc dựng baseline dù đã có 1 lần thử vá không thành công trước đó (helm upgrade bị API server từ chối vì `requests > limits`). Chu kỳ sống giữa các lần crash đang ngắn dần (~3 phút ở lần gần nhất). Tương quan với Jaeger: 2 lần crash gần-đồng-thời trong ngày (19 giây và ~1 phút cách nhau) — đáng cân nhắc cho 1 nguyên nhân chung (nghi vấn traffic từ CloudFront, chưa xác nhận qua ingestion rate thật).
- *Ảnh hưởng khách hàng:*
  Không ảnh hưởng trực tiếp khách hàng (Grafana không nằm trên luồng mua hàng), nhưng team **mất khả năng quan sát hệ thống ngay lúc cần nhất** nếu có incident khác xảy ra cùng lúc — ảnh hưởng gián tiếp tới tốc độ phản ứng mọi sự cố khác.
- *Rủi ro (khả năng × mức nghiêm trọng):*
  Khả năng đã xảy ra thật, đang tiếp diễn (không phải giả định) × nghiêm trọng cao (mù quan sát đúng lúc cần) = **P0**.
- *Tác động business (SLO/BUDGET/INCIDENT_HISTORY):*
  Gián tiếp nhưng nghiêm trọng — ảnh hưởng MTTR (mean time to recovery) của mọi luồng khác.
- *Giải pháp đề xuất:*
  Tăng memory Grafana lên tối thiểu `requests: 512Mi` / `limits: 1Gi` trong Helm values (bắt buộc tăng **cả 2**, không chỉ requests — Kubernetes yêu cầu `requests ≤ limits`, lần thử trước bị fail đúng vì bỏ sót điều này). Rà lại số sidecar/dashboard đang bật. Đưa `jaeger.resources.limits.memory` (hiện 600Mi) vào cùng đợt review.
- *Chi phí / effort:*
  Rất thấp — chỉ đổi số trong values, ~15 phút, thêm ~700Mi memory cho 1 pod (không đáng kể so với trần $300/tuần).
- *Acceptance criteria:*
  Grafana restart count không tăng trong ≥1-2 giờ theo dõi sau rollout; `/grafana/api/health` trả `200` ổn định; dashboard load được khi có traffic/loadgen chạy.
- *Rollback / nếu làm sai:*
  `helm rollback techx-corp <revision trước>`. Phát hiện sai (VD limit mới vẫn không đủ) qua `kubectl get pods` restart count tiếp tục tăng — vài phút nếu theo dõi chủ động, lâu hơn nếu không (phụ thuộc REL-15).

## REL-14 — Điều tra và vá crash history của `product-catalog`
*Trụ:* Reliability · *Ưu tiên đề xuất:* P1 · *Owner:* Chưa gán

- *Evidence:*
  Pod `product-catalog-d769b79c4-j7wp7`: `Restart Count: 3`, `Last Reason: Error`, `Exit Code: 1`, `memory limit: 20Mi`, `GOMEMLIMIT: 16MiB`. Pattern lặp lại xác nhận qua 2 thế hệ pod khác nhau (1 pod 37h tuổi và 1 pod mới hơn) — **cả 2 đều crash đúng 3 lần** ngay sau khi khởi động rồi ổn định, gợi ý lỗi khởi động có tính lặp (khả năng cao: race condition chờ Postgres sẵn sàng), không phải ngẫu nhiên.
- *Ảnh hưởng khách hàng:*
  `product-catalog` nằm thẳng trên đường business chính (danh mục sản phẩm) — trong lúc pod đang crash-loop lúc khởi động, khách có thể gặp lỗi khi duyệt sản phẩm nếu đúng lúc pod đó chưa qua khỏi vòng crash 3 lần.
- *Rủi ro (khả năng × mức nghiêm trọng):*
  Khả năng cao (crash tái diễn ở mọi lần khởi động mới, đã quan sát 2 lần độc lập) × nghiêm trọng cao (đường business chính) = **P1**.
- *Tác động business (SLO/BUDGET/INCIDENT_HISTORY):*
  Cùng service với REL-05 (thiếu connection pool Postgres) — khả năng cao 2 vấn đề cộng hưởng, memory 20Mi rất thấp có thể là nguyên nhân trực tiếp của crash lúc khởi động.
- *Giải pháp đề xuất:*
  Lấy log `--previous` ngay lần crash tiếp theo để xác định nguyên nhân chính xác; tăng memory limit hợp lý dựa trên số liệu (không đoán); làm cùng đợt với REL-05/REL-07.
- *Chi phí / effort:*
  Rất thấp cho việc đổi memory limit (~15 phút) + thời gian điều tra log (~1-2 giờ).
- *Acceptance criteria:*
  Không có restart mới sau rollout/load test; có bằng chứng log/metric giải thích được nguyên nhân 3 lần crash cũ, hoặc chấp nhận rủi ro có ghi chú rõ ràng nếu không tái hiện được.
- *Rollback / nếu làm sai:*
  `helm upgrade` trả memory limit về giá trị cũ. Phát hiện qua `kubectl get pods` restart count — vài phút.

## REL-15 — Thêm alerting cho restart/OOM/readiness fail
*Trụ:* Reliability / Observability · *Ưu tiên đề xuất:* P1 · *Owner:* Chưa gán

- *Evidence:*
  Toàn bộ REL-13, REL-14 và các warning readiness đều bị phát hiện **thủ công** qua `describe`/`events`, không qua alert nào. `kubectl get pdb -A` chỉ thấy PDB cho `coredns`/`opensearch-pdb`. Grafana đang down thật (REL-13) là ví dụ sống: không ai biết dashboard chính đang chết nếu không tự tay `kubectl get pods` kiểm tra.
- *Ảnh hưởng khách hàng:*
  Không trực tiếp, nhưng gián tiếp kéo dài thời gian khách hàng chịu ảnh hưởng của mọi sự cố khác vì team phát hiện chậm.
- *Rủi ro (khả năng × mức nghiêm trọng):*
  Khả năng cao (đã chứng minh — mọi phát hiện gần đây đều thủ công) × nghiêm trọng cao (ảnh hưởng MTTR toàn hệ thống) = **P1**.
- *Tác động business (SLO/BUDGET/INCIDENT_HISTORY):*
  Ảnh hưởng trực tiếp tốc độ MTTR cho mọi sự cố khác, kể cả sự cố BTC bơm vào qua flagd.
- *Giải pháp đề xuất:*
  Thêm Grafana alert rule cho: restart count tăng, OOMKilled, readiness probe fail liên tục >N phút, service checkout path unavailable. Tận dụng structure có sẵn ở `grafana/provisioning/alerting/cart-service-alerting.yml` làm mẫu, nhân rộng ra service khác. **Nên làm sau khi REL-01/REL-13/REL-14 ổn định** để tránh alert nhiễu ngay từ đầu.
- *Chi phí / effort:*
  Thấp — chỉ cấu hình alert rule trong Grafana, không cần thêm hạ tầng mới. ~2-3 giờ-người.
- *Acceptance criteria:*
  Alert fire được khi giả lập restart/OOM thủ công (VD giới hạn memory 1 pod test xuống rất thấp để trigger OOM có kiểm soát); có runbook ngắn kèm theo mỗi alert.
- *Rollback / nếu làm sai:*
  Tắt/xóa alert rule qua Grafana provisioning nếu gây nhiễu (false positive quá nhiều) — phát hiện ngay lập tức qua số lượng alert bất thường.

---

## COST OPTIMIZATION

## COST-01 — Viết lại ECR lifecycle policy đúng cách (scoped theo `tagPrefixList`)
*Trụ:* Cost Optimization · *Ưu tiên đề xuất:* P1 · *Owner:* Chưa gán

- *Evidence:*
  Lifecycle policy cũ đã bị xóa do gây sự cố (xem `docs/postmortem/0001-...md`) — hiện **không có cơ chế dọn image cũ nào** trên ECR.
- *Ảnh hưởng khách hàng:*
  Không ảnh hưởng khách hàng trực tiếp — thuần túy chi phí lưu trữ.
- *Rủi ro (khả năng × mức nghiêm trọng):*
  Khả năng cao (đang build/push lại nhiều lần trong 3 tuần) × nghiêm trọng thấp-trung bình = **P1** (dọn nợ tự gây, nên làm sớm nhưng không khẩn cấp bằng nhóm P0).
- *Tác động business (SLO/BUDGET/INCIDENT_HISTORY):*
  ECR storage rẻ nhưng cộng dồn 3 tuần + nhiều lần CI chạy có thể đáng kể trong trần $300/tuần.
- *Giải pháp đề xuất:*
  Viết lại lifecycle policy dùng `tagPrefixList` riêng cho từng service (rút kinh nghiệm từ chính sự cố cũ), test trên môi trường không ảnh hưởng trước khi áp dụng lên ECR thật.
- *Chi phí / effort:*
  Thấp — ~1-2 giờ-người viết + test policy.
- *Acceptance criteria:*
  Policy áp dụng không xóa nhầm image đang được dùng bởi Helm release hiện tại (test bằng cách áp policy trên ECR repo test trước); image cũ hơn ngưỡng đặt (VD >10 bản/service) bị dọn tự động.
- *Rollback / nếu làm sai:*
  Xóa lifecycle policy qua `aws ecr delete-lifecycle-policy` ngay lập tức nếu phát hiện xóa nhầm image đang dùng — cần phát hiện nhanh vì image bị xóa không phục hồi được (đây chính là nguyên nhân sự cố cũ), nên **bắt buộc test kỹ trước khi áp production**.

## COST-02 — Cài Cluster Autoscaler thật
*Trụ:* Cost Optimization · *Ưu tiên đề xuất:* P1 · *Owner:* Chưa gán

- *Evidence:*
  IRSA cho Cluster Autoscaler đã chuẩn bị sẵn trong Terraform (`cluster_autoscaler_role_arn` output) nhưng **chưa cài đặt chart thật**. Xác nhận qua evidence chéo (phucdo, 09/07): không thấy pod `cluster-autoscaler` hay `karpenter` nào trong cluster; ASG `Desired=3, Min=3, Max=6` — chỉ là khả năng mở rộng của ASG, không có controller thì cluster không tự scale.
- *Ảnh hưởng khách hàng:*
  Không ảnh hưởng trực tiếp — có thể gián tiếp nếu tải tăng đột biến mà không có gì tự scale thêm node.
- *Rủi ro (khả năng × mức nghiêm trọng):*
  Khả năng cao (đang trả tiền 3 node 24/7 chắc chắn) × nghiêm trọng trung bình (lãng phí chi phí, không phải outage) = **P1** — phụ thuộc REL-07 (cần CPU requests để autoscaler tính đúng).
- *Tác động business (SLO/BUDGET/INCIDENT_HISTORY):*
  Trực tiếp vào ngân sách $300/tuần — ước tính ~$42/tuần cho node cố định dù tải ban đêm gần như bằng 0.
- *Giải pháp đề xuất:*
  Cài `cluster-autoscaler` Helm chart dùng IRSA role đã có sẵn, cấu hình scale-down khi tải thấp. **Chưa nên tối ưu scale-down quá mạnh trước khi có đủ số liệu** (theo khuyến nghị chéo từ phucdo).
- *Chi phí / effort:*
  Thấp effort (hạ tầng đã chuẩn bị sẵn, chỉ cần `helm install`) — nhưng phụ thuộc REL-07 xong trước.
- *Acceptance criteria:*
  Pod `cluster-autoscaler` `Running`; log cho thấy autoscaler đọc được ASG/nodegroup không lỗi permission; có bằng chứng scale decision (log quyết định scale, dù chưa cần thực sự scale).
- *Rollback / nếu làm sai:*
  `helm uninstall cluster-autoscaler`. Nếu scale-down quá mạnh gây thiếu node đúng lúc tải cao, phát hiện qua pod `Pending` — vài phút.

## COST-03 — Chuyển workload chịu được gián đoạn sang Spot instance
*Trụ:* Cost Optimization · *Ưu tiên đề xuất:* P2 · *Owner:* Chưa gán

- *Evidence:*
  Hiện toàn bộ 3 node đều `t3.large` on-demand, chưa dùng Spot cho bất kỳ workload nào.
- *Ảnh hưởng khách hàng:*
  Không ảnh hưởng nếu chỉ áp dụng cho `load-generator`/`recommendation`/`ad` (không quan trọng bằng nhóm checkout).
- *Rủi ro (khả năng × mức nghiêm trọng):*
  Khả năng thấp (chưa làm) × nghiêm trọng thấp nếu làm đúng thứ tự sau REL-01 = **P2**.
- *Tác động business (SLO/BUDGET/INCIDENT_HISTORY):*
  Tiềm năng tiết kiệm ~60-70% chi phí node cho phần tải chịu được gián đoạn.
- *Giải pháp đề xuất:*
  **Chỉ làm sau khi REL-01 xong** — dùng Spot khi còn `replicas:1` sẽ khuếch đại đúng rủi ro Reliability đang cố sửa. Thêm node group riêng cho Spot, tách theo nhãn workload (`load-generator`, `recommendation`, `ad`).
- *Chi phí / effort:*
  Trung bình — cần thêm node group riêng, taint/toleration cho workload phù hợp.
- *Acceptance criteria:*
  Node Spot chạy ổn định ≥24h không bị terminate bất ngờ ảnh hưởng service; chi phí node giảm đo được qua Cost Explorer.
- *Rollback / nếu làm sai:*
  Xóa node group Spot, chuyển workload về node group on-demand cũ qua `kubectl cordon`/`drain`. Phát hiện Spot bị reclaim qua CloudWatch/node event — vài phút.

## COST-04 — Right-size instance type sau khi có số liệu CPU thật
*Trụ:* Cost Optimization · *Ưu tiên đề xuất:* P2 · *Owner:* Chưa gán

- *Evidence:*
  Đang chọn `t3.large` x3 dựa trên ước tính thô, chưa có số liệu CPU thật để biết đang thừa hay thiếu (phụ thuộc REL-07 hoàn thành).
- *Ảnh hưởng khách hàng:*
  Không ảnh hưởng trực tiếp.
- *Rủi ro (khả năng × mức nghiêm trọng):*
  Khả năng trung bình × nghiêm trọng trung bình (có thể đang trả tiền thừa hoặc thiếu mà không biết) = **P2**.
- *Tác động business (SLO/BUDGET/INCIDENT_HISTORY):*
  Ảnh hưởng hiệu quả sử dụng ngân sách $300/tuần, không phải SLO.
- *Giải pháp đề xuất:*
  Sau khi có REL-07 (CPU requests/limits) + chạy vài ngày thực tế, xem lại `node_instance_type`/số node trong Terraform.
- *Chi phí / effort:*
  Thấp effort (chỉ đổi biến Terraform), nhưng cần dữ liệu trước.
- *Acceptance criteria:*
  Có bảng so sánh CPU request/limit vs usage thật; quyết định đổi/giữ instance type có số liệu kèm theo, không phải ước tính.
- *Rollback / nếu làm sai:*
  `terraform apply` với `node_instance_type` cũ nếu instance mới không đủ tải — cần ADR trước khi đổi vì đây là thay đổi tốn tiền theo `BUDGET.md`.

## COST-05 — Giảm memory limit `load-generator` nếu không cần thiết
*Trụ:* Cost Optimization · *Ưu tiên đề xuất:* P2 · *Owner:* Chưa gán

- *Evidence:*
  `load-generator` được cấp 1500Mi memory — cao bất thường, chiếm ~17% tổng memory limit cộng dồn toàn hệ thống.
- *Ảnh hưởng khách hàng:*
  Không ảnh hưởng — đây là bot giả lập traffic, không phục vụ khách thật.
- *Rủi ro (khả năng × mức nghiêm trọng):*
  Khả năng thấp-trung bình × nghiêm trọng thấp = **P2**.
- *Tác động business (SLO/BUDGET/INCIDENT_HISTORY):*
  Nhỏ nhưng dễ sửa — giải phóng memory budget cho các mục khác cần hơn (VD REL-13 Grafana).
- *Giải pháp đề xuất:*
  Thử giảm memory limit và quan sát — có thể đây chỉ là giá trị mặc định từ chart gốc chưa tối ưu cho quy mô TF3.
- *Chi phí / effort:*
  Rất thấp — chỉ cần thử giảm và quan sát, ~30 phút.
- *Acceptance criteria:*
  `load-generator` chạy ổn định ở memory limit mới thấp hơn, không bị OOMKilled trong ≥1 giờ theo dõi.
- *Rollback / nếu làm sai:*
  `helm upgrade` trả memory limit về 1500Mi nếu `load-generator` bị OOMKilled — phát hiện ngay qua `kubectl get pods`.

## COST-06 — Áp dụng `ResourceQuota` mẫu (`deploy/quota.yaml`)
*Trụ:* Cost Optimization · *Ưu tiên đề xuất:* P2 · *Owner:* Chưa gán

- *Evidence:*
  `requests` thực ra đã tồn tại (đính chính đầu doc) — quota có thể áp dụng mà không làm gãy pod như lo ngại ban đầu. Đối chiếu số hiện tại: `requests.memory` cộng dồn ~8.6Gi, quota mẫu đặt `requests.memory: 8Gi` — **sát nút**, cần điều chỉnh trước khi áp.
- *Ảnh hưởng khách hàng:*
  Không ảnh hưởng nếu áp đúng số; nếu áp sai (quota quá chặt), có thể chặn deploy mới, gián tiếp chặn cả việc vá lỗi khác.
- *Rủi ro (khả năng × mức nghiêm trọng):*
  Khả năng thấp (nếu điều chỉnh số đúng trước khi áp) × nghiêm trọng trung bình nếu áp sai (chặn nhầm REL-01) = **P2**.
- *Tác động business (SLO/BUDGET/INCIDENT_HISTORY):*
  Giúp kiểm soát chi phí namespace tổng thể, không ảnh hưởng SLO nếu làm đúng thứ tự.
- *Giải pháp đề xuất:*
  Điều chỉnh số trong `quota.yaml` cho khớp thực tế **sau khi làm xong REL-01 + REL-07**, rồi mới áp dụng — áp quá sớm sẽ tự chặn chính công việc REL-01.
- *Chi phí / effort:*
  Thấp — ~1 giờ điều chỉnh + áp dụng.
- *Acceptance criteria:*
  Quota áp dụng không chặn bất kỳ deploy hợp lệ nào trong tuần kế tiếp; tổng resource request namespace nằm trong quota với margin ≥10%.
- *Rollback / nếu làm sai:*
  `kubectl delete resourcequota` ngay lập tức nếu quota chặn nhầm deploy quan trọng — phát hiện ngay lập tức qua lỗi `helm upgrade`/`kubectl apply` bị từ chối.

## COST-07 (đã làm, nêu để ghi công) — NAT Gateway đơn thay vì 1/AZ
*Trụ:* Cost Optimization · *Ưu tiên đề xuất:* Đã hoàn thành · *Owner:* arthur (lúc dựng baseline)

- *Evidence:* `infra/` — quyết định kiến trúc ban đầu chọn 1 NAT Gateway thay vì 3.
- *Ảnh hưởng khách hàng:* Không ảnh hưởng (khác biệt độ trễ không đáng kể trong phạm vi 1 VPC).
- *Rủi ro:* Đã chấp nhận từ đầu — SPOF tầng network nếu AZ chứa NAT gặp sự cố, đánh đổi lấy chi phí thấp hơn.
- *Tác động business:* Tiết kiệm ~2/3 chi phí NAT so với phương án 1 NAT/AZ.
- *Giải pháp:* Đã triển khai — nêu trong Pitch như bằng chứng đã có tư duy cost-conscious ngay từ lúc dựng baseline.
- *Chi phí / effort:* Đã chi, không phát sinh thêm.
- *Acceptance criteria:* Đã đạt — hệ thống vận hành ổn định với 1 NAT Gateway từ baseline tới nay.
- *Rollback:* Đổi `nat_gateway_count` trong `terraform.tfvars` lên 3 nếu cần Multi-AZ NAT sau này — cần ADR vì đây là thay đổi tốn tiền.

---

## Ghi chú bổ sung (không phải backlog item, giữ lại để trả lời hội đồng chính xác)

- **AI/LLM:** đọc code xác nhận `llm` service hiện là **mock hoàn toàn** — trả lời/tóm tắt từ dữ liệu tĩnh định sẵn (`product-review-summaries.json`), không gọi LLM thật. Việc cắm LLM thật thuộc phạm vi AIO02 (`values-aio-llm.yaml`), không phải việc của CDO02.
- **metrics-server:** xác nhận không tồn tại trong cluster (`kubectl top nodes` → `Metrics API not available`) — khớp với việc CDO02 đã tự cài thử rồi gỡ trong phiên làm việc sáng 09/07. Cần cài lại trước khi làm REL-06/REL-07/COST-04 (đều phụ thuộc số liệu CPU/memory thật).
- **Auditability:** đã có 1 lần `helm upgrade` thử vá REL-13 bị fail do sai cấu hình (`requests > limits`) — không ghi chi tiết người thực hiện vào đây theo yêu cầu, chỉ ghi nhận để nhắc quy trình: mọi thay đổi hạ tầng nên có ADR trước khi apply, kể cả thử nghiệm nhanh.

---

## Thứ tự đề xuất thực thi

**Đã đổi sang bám sát đúng mục 4 của Meeting note liên team (09/06)** — thứ tự này là thứ tự chung cả 3 team thống nhất, không phải chỉ riêng CDO02 tự xếp nữa. Ghi theo mã P chung, kèm mã CDO02 và owner để biết phần nào CDO02 trực tiếp làm.

1. **P01 + P02** (REL-02 + REL-03) — sửa health check thật + thêm probe. *CDO02 chủ trì P01, phối hợp CDO01 ở P02.*
2. **P03** (REL-01) — tăng replicas checkout path. *CDO02 phối hợp CDO01.*
3. **P04 + P05 + P06** (REL-04 + REL-09) — rollback checkout, sửa accounting/Kafka mất đơn âm thầm. *CDO02 chủ trì cả 3, không cần CDO01.*
4. **P07 + P08** (metrics-server, baseline load test/RED) — *CDO01 chủ trì, CDO02 không cần tự làm (đã bàn giao qua meeting).*
5. **P09 + P10** (REL-13 + REL-15) — sửa Grafana/Jaeger OOM + thêm alert. *CDO02 phối hợp CDO01, P09 đang active ngay lúc này (xem REL-13).*
6. **P15 + P16** (NetworkPolicy + ingress boundary) — *CDO01 chủ trì. CDO02 cần theo sát P16 vì đụng trực tiếp `infra/cloudfront.tf` mình vừa dựng.*
7. **P11 + P12 + P22** (HPA, CPU requests/limits, Cluster Autoscaler/Karpenter) — *CDO01 chủ trì hoàn toàn, không còn là việc CDO02 (meeting đã chuyển giao).*

**Phần CDO02 tự làm thêm, ngoài phạm vi P01-P25 (không có mã P chung):**
- **P1 nội bộ:** REL-05 (P13), REL-10 phần Valkey (P14) — đã có mã P, thứ tự nằm trong bước 3-4 ở trên theo phụ thuộc riêng (REL-05 phụ thuộc REL-01/02/03 xong trước).
- **P2 nội bộ (khi còn thời gian):** COST-01 (ECR lifecycle), COST-03 (Spot), COST-04 (right-size), COST-05 (giảm memory load-generator), REL-11 (currency validate), REL-12 (quote validate).

**Theo dõi, không chủ động làm:** REL-08 (và phần Postgres/Kafka trong REL-10) — chờ mandate BTC. Không có mã P tương ứng trong meeting, đúng như đánh giá ban đầu — không ai trong 3 team yêu cầu làm sớm.

**Đã hoàn thành, nêu để ghi công:** COST-07 (NAT Gateway đơn).
