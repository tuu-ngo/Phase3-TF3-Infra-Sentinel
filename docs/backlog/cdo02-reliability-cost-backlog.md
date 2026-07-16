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

## Đối chiếu với Meeting note liên team (09/07, AI + CDO01 + CDO02)

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

## SLO hiện tại — đo trực tiếp qua Prometheus (10/07, ~09:28 ICT)

Đo đúng công thức trong `SLO.md` (cửa sổ rolling 24h), query trực tiếp `traces_span_metrics_calls_total`/`traces_span_metrics_duration_milliseconds_bucket` qua Prometheus port-forward — không phải ước tính.

| Luồng | SLO yêu cầu | Đo được (rolling 24h) | Kết quả |
|---|---|---|---|
| Duyệt sản phẩm (non-5xx) | ≥ 99.5% | **99.74%** | ✅ Đạt |
| Duyệt sản phẩm (p95 latency) | < 1000ms | **58.8ms** | ✅ Đạt rất thoải mái |
| Giỏ hàng | ≥ 99.5% | **~100%** (0 lỗi / 298.339 request) | ✅ Đạt |
| **Checkout** | **≥ 99.0%** | **98.96%** (143.247 OK + 1.501 lỗi / 144.748 tổng) | 🔴 **VI PHẠM SLO** |

**🔴 Checkout vi phạm SLO — đã điều tra ra nguyên nhân gốc, đã tự phục hồi:**
Bẻ nhỏ theo khung 2h trong 24h qua cho thấy **toàn bộ 1.511 lỗi dồn vào đúng khung `02:28-06:28 UTC` ngày 09/07** — trước và sau khung đó là **0 lỗi hoàn toàn** (đã sạch liên tục ~20 giờ tính đến lúc đo). Đối chiếu thời gian: khung lỗi này **trùng khớp chính xác** với đợt rolling-replace 3 node do `terraform apply` (PR #17 merge) gây ra lúc `03:43-03:54 UTC` — hệ quả phụ của việc đồng bộ K8s version node group 1.31→1.32 để khớp control plane.

**Ý nghĩa cho Pitch:** đây là **bằng chứng định lượng đầu tiên, thực đo, không phải suy luận**, chứng minh trực tiếp REL-01/P03 (thiếu replicas + PDB) — 1.511 request checkout của khách hàng thật đã lỗi vì không có bản dự phòng đúng lúc node bị thay. Vì cửa sổ đo rolling 24h, số 98.96% sẽ tự "sạch" dần về ~100% trong vài giờ tới khi khung lỗi trôi khỏi cửa sổ — **dùng ngay số liệu này trong Pitch trước khi nó tự trôi qua**, đừng chờ tới lúc SLO đã "xanh" trở lại rồi mới trình bày.

---

## RELIABILITY

## REL-01 — Tăng replicas ≥2 cho nhóm checkout + thêm PodDisruptionBudget
*Trụ:* Reliability · *Ưu tiên đề xuất:* P0 · *Owner:* Chưa gán — cần chốt trong họp CDO01/CDO02

- *Evidence:*
  `techx-corp-chart/values.yaml`: `default.replicas: 1` áp dụng toàn bộ ~18 app component, không override cho `cart`/`checkout`/`payment`/`currency`/`product-catalog`/`shipping`. Xác nhận lại trên runtime (evidence chéo từ phucdo, 09/07): `kubectl -n techx-tf3 get deploy` — toàn bộ deployment app đang `DESIRED=1`/`AVAILABLE=1`. `kubectl get pdb -A` chỉ thấy PDB cho `coredns` và `opensearch-pdb` — **không có PDB nào bảo vệ checkout path**.
  **Bằng chứng định lượng mới (10/07, đo qua Prometheus):** checkout success rate rolling-24h đo được **98.96%** (144.748 request, 1.501 lỗi) — **vi phạm SLO ≥99.0%**. Bẻ nhỏ theo khung 2h xác nhận toàn bộ 1.511 lỗi dồn vào đúng khung `02:28-06:28 UTC` 09/07, trùng khớp chính xác với đợt rolling-replace 3 node do `terraform apply` gây ra (`03:43-03:54 UTC`, PR #17). Trước/sau khung đó: 0 lỗi. Đây là bằng chứng thực đo đầu tiên, không phải suy luận từ INC-2 nữa.
- *Ảnh hưởng khách hàng:*
  1 pod chết (crash, node drain, OOM) = mất hoàn toàn 1 chặng trong luồng mua hàng trong lúc pod restart (vài giây tới vài chục giây tùy readiness). Khách đang ở giữa flow checkout gặp lỗi 5xx hoặc timeout. **Đã xảy ra thật 09/07: 1.511 request checkout lỗi trong ~4 giờ.**
- *Rủi ro (khả năng × mức nghiêm trọng):*
  Khả năng **cao, đã đo được thật** (checkout SLO breach 09/07, xem dưới) × nghiêm trọng cao (đụng thẳng luồng ra tiền) = **P0**.
- *Tác động business (SLO/BUDGET/INCIDENT_HISTORY):*
  Checkout SLO ≥99% (`SLO.md`) — **đã thực sự bị vi phạm** (98.96% đo được 10/07 sáng, cửa sổ rolling 24h sẽ tự sạch lại trong vài giờ tới nhưng sự việc đã xảy ra thật). *Lưu ý cite chính xác để không bị bắt lỗi:* **INC-2** trong `INCIDENT_HISTORY.md` là sự cố **mất giỏ hàng** — nguyên nhân gốc single-replica của nó liên quan mục này, nhưng phần data-loss thuộc **REL-10** (đừng gán trọn INC-2 cho REL-01). Bằng chứng trực tiếp và mạnh nhất cho REL-01 là **sự kiện đo được 09/07** (node version sync rolling-replace → 1.511 lỗi checkout), không phải INC-2. INC-2 chỉ củng cố "bài học còn treo: vài thành phần vẫn là SPOF".
- *Giải pháp đề xuất:*
  Set `replicas: 2` cho `cart`, `checkout`, `payment`, `currency`, `product-catalog`, `shipping` trong values override; thêm `PodDisruptionBudget` (`minAvailable: 1`) cho từng service này; cân nhắc `topologySpreadConstraints` để tránh 2 pod cùng node.
- *Chi phí / effort:*
  ~2-3 giờ-người (sửa values + test). **Chi phí hạ tầng = $0 (đã kiểm chứng, không phải ước lượng):** 6 service này limit nhỏ (20–160Mi), nhân đôi chỉ thêm ~0.5–1Gi RAM tổng. Node hiện dùng 27–41% memory / 12–64% CPU requests (`kubectl describe node`) → thừa headroom, **không cần thêm node → không phát sinh chi phí**. Multi-AZ spread cũng $0 vì đã sẵn 3 node/3 AZ, chỉ thêm `topologySpreadConstraints` (config). Đối chiếu `BUDGET.md`: run-rate hiện ~$95/tuần (~1/3 trần $300), 3 node t3.large là line lớn nhất (~$53/tuần). *(Multi-AZ tốn tiền thật = managed DB Multi-AZ ~gấp đôi — đó là REL-08, cố ý hoãn.)*
- *ROI:*
  Chi phí $0, tác động = bảo vệ trực tiếp checkout SLO đã **đo được vi phạm thật** hôm qua (98.96%, ~1.500 đơn fail). Reliability win rẻ nhất có thể có — đây là lý do xếp P0, không phải vì tốn kém mới quan trọng.
- *Acceptance criteria:*
  `kubectl get deploy` cho 6 service trên hiển thị `AVAILABLE=2`; PDB tồn tại và `ALLOWED DISRUPTIONS ≥1`; **bài failover test bắt buộc:** kill thủ công 1 pod trong nhóm (`kubectl delete pod`) VÀ drain thử 1 node (`kubectl drain --ignore-daemonsets`), xác nhận checkout success-rate không tụt dưới SLO trong suốt quá trình (đo qua Prometheus, không chỉ quan sát mắt). Đây chính là bài test mà đợt rolling-replace hôm qua đã cho thấy trạng thái hiện tại **trượt**.
- *Rollback / nếu làm sai:*
  `helm upgrade --install techx-corp ... --set <service>.replicas=1` để trả lại giá trị cũ (kèm lại `-f values-flagd-sync.yaml`, bắt buộc theo GETTING_STARTED.md). Nếu replicas mới gây thiếu tài nguyên node (Pending), phát hiện ngay qua `kubectl get pods` (vài phút) do pod không schedule được.

## REL-02 — Sửa health check giả thành kiểm tra dependency thật
*Trụ:* Reliability · *Ưu tiên đề xuất:* P0 · *Owner:* CDO02 · **✅ ĐÃ LÀM + DEPLOYED (verify 15/07)**

> **Cập nhật 15/07:** Đã hoàn thành, code đã merge + nằm trong image đang chạy (commit `8ce45af`
> "make product-catalog health check reflect its DB dependency", `e6a3717` "extend real health checks";
> image `6a3fe95-product-catalog`, `7527509-checkout`). Service có dependency stateful đã dùng gRPC
> readiness → Health service dependency-aware: **product-catalog** (`db.PingContext` mỗi 5s → NOT_SERVING),
> **product-reviews** (`Check()` kiểm DB, grpc:3551), **checkout** (`dependencyHealthStatus()`, grpc:8080).
> Service **stateless** (currency/ad/payment/recommendation → không có DB/Kafka/Redis ngoài) giữ static
> SERVING là **đúng** — không có dependency để check, đánh dấu NOT_SERVING sẽ sai. Còn lại chỉ
> **acceptance test live** (chặn Postgres tạm → health flip NOT_SERVING ≤1 chu kỳ probe) — gộp vào phần
> demo/live-test Mandate #3.

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
- *Cập nhật hiện trạng (14/07 — audit live trên account mới `197826770971`):*
  Đã có tiến triển một phần. **4 app service ĐÃ được thêm gRPC probe** qua `values-prod.yaml` (verify pod Ready, probe đang pass — **cơ chế health check hoạt động tốt**): `checkout`, `product-catalog`, `recommendation` (readiness `grpc:8080` / liveness `tcp:8080`); `product-reviews` (`grpc:3551` / `tcp:3551`).
  **Còn THIẾU cả 2 probe — 14 app service + 3 datastore:** `accounting, ad, cart, currency, email, frontend, frontend-proxy, fraud-detection, image-provider, kafka, llm, payment, quote, shipping` + datastore `postgresql, valkey-cart, kafka`. (`load-generator`, `grafana` bỏ qua — tool/subchart.)
  *Bằng chứng tươi:* `shipping` bị báo "có vẻ chết" (14/07) — điều tra ra pod vẫn Running và **serve đúng** ($8.99 phí ship, HTTP 200); "chết" chỉ vì **không có probe = không tín hiệu sống**. Đúng rủi ro mục này cảnh báo: thiếu liveness → service treo dưới tải 200 user không bị restart; thiếu readiness → vẫn route traffic vào pod hỏng.
  *Probe type theo service khi triển khai nốt:* service gRPC → `grpc:<port>`; `frontend`/`frontend-proxy` (HTTP) → `httpGet /`; datastore → `tcpSocket` hoặc exec (`pg_isready` cho postgres, `valkey-cli ping` cho valkey, tcp cho kafka). Threshold + nguyên tắc liveness-lỏng-hơn-readiness giữ như phần *Giải pháp* bên dưới.
- *Ảnh hưởng khách hàng:*
  Mỗi lần deploy/rollout, K8s route traffic vào pod mới trước khi pod thật sự sẵn sàng nhận request → khách gặp lỗi ngay lúc deploy (đúng kịch bản đã xảy ra ở INC-3, lỗi thanh toán lúc deploy).
- *Rủi ro (khả năng × mức nghiêm trọng):*
  Khả năng cao (xảy ra ở **mọi lần** rollout) × nghiêm trọng cao (đã gây lỗi thanh toán thật) = **P0**.
- *Tác động business (SLO/BUDGET/INCIDENT_HISTORY):*
  Nguyên nhân gốc xác nhận của INC-3, **vẫn chưa được vá tới giờ**. Mỗi lần deploy/rollout trong 3 tuần còn lại có nguy cơ tái diễn.
- *Giải pháp đề xuất:*
  Thêm `readinessProbe`/`livenessProbe` (gRPC health check hoặc HTTP `/healthz` tùy service) cho toàn bộ component, ưu tiên nhóm checkout. **Phụ thuộc REL-02** — probe vô nghĩa nếu health check backend vẫn giả.
  **Threshold đề xuất cụ thể (không đặt chung chung, sẵn sàng bảo vệ trước SRE):**
  - *readinessProbe* (chỉ gỡ pod khỏi Service endpoint — an toàn, được phép nhạy hơn): `periodSeconds: 5`, `timeoutSeconds: 2`, `failureThreshold: 3`, `successThreshold: 1` (→ ~15s lỗi mới gỡ khỏi rotation). `initialDelaySeconds` tách theo tốc độ khởi động: Go/Rust/C++ (`checkout`/`currency`/`product-catalog`/`shipping`) ~5s; .NET/Java/Ruby (`accounting`/`ad`/`email`) ~15–20s.
  - *livenessProbe* (giết + restart pod — nguy hiểm, **cố ý nới lỏng hơn readiness**): `periodSeconds: 10`, `timeoutSeconds: 3`, `failureThreshold: 5` (→ ~50s lỗi liên tục mới kill, tránh giết pod vì blip tạm thời).
  - **Nguyên tắc bắt buộc:** readiness check dependency thật (từ REL-02); liveness **chỉ** check process còn phản hồi, **KHÔNG** check dependency — nếu không, lúc Postgres/Kafka sập, liveness fail đồng loạt → K8s restart mọi pod cùng lúc → cascading failure, tệ hơn tình trạng ban đầu.
- *Chi phí / effort:*
  Thấp — chủ yếu cấu hình YAML, ~2-3 giờ-người cho toàn bộ chart. Chi phí hạ tầng $0.
- *Acceptance criteria:*
  `kubectl rollout restart deploy/checkout` (và nhóm checkout) không làm checkout success-rate tụt dưới SLO trong suốt rollout (đo qua Prometheus, gọi liên tục vào storefront). Test cả trường hợp probe hoạt động đúng: tắt tạm dependency của 1 service → pod đó phải bị gỡ khỏi rotation (readiness fail) nhưng **không** bị restart hàng loạt (liveness không được fail theo).
- *Rollback / nếu làm sai:*
  `helm rollback techx-corp <revision trước>`. Rủi ro chính khi làm sai: (a) readiness quá gắt → pod flap khỏi rotation, giảm capacity ảo — thấy qua ready/restart metric; (b) liveness quá gắt → crashloop dây chuyền dưới tải (tệ nhất). Giảm thiểu: liveness luôn lỏng hơn readiness (đã thiết kế ở trên), roll out nhóm ngoài-checkout trước + theo dõi restart count 1–2h, phát hiện qua `kubectl get pods` (READY/RESTARTS bất thường).

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
  `values.yaml` (`valkey-cart`): không RDB, không AOF, không PVC. Runtime: `kubectl get pv,pvc -A` → **không có PV/PVC nào trong toàn cluster** — nghĩa là Postgres và Kafka cũng hoàn toàn không có persistent storage, không riêng Valkey. **Đây là nguyên nhân gốc chính xác của INC-2** (`INCIDENT_HISTORY.md`): "mất giỏ hàng sau khi node được lên lịch lại — lớp lưu giỏ hàng chạy đơn lẻ, state trong bộ nhớ mất theo". INC-2 map trực tiếp vào mục này, không phải suy diễn.
- *Ảnh hưởng khách hàng:*
  Restart pod `valkey-cart` (deploy, node drain, OOM) = khách đang có giỏ hàng mất sạch, phải thêm lại từ đầu — **đã xảy ra thật ở INC-2**. Nếu là Postgres/Kafka: mất dữ liệu sản phẩm/review/đơn hàng đã ghi vĩnh viễn.
- *Rủi ro (khả năng × mức nghiêm trọng):*
  Valkey: khả năng **cao** (đã xảy ra thật ở INC-2, và `valkey-cart` vẫn 1 replica + 0 persistence tới giờ — chưa vá) × nghiêm trọng trung bình = **P1**. Postgres/Kafka: nghiêm trọng rất cao nhưng trùng phạm vi REL-08 (chờ mandate) → giữ ở mức theo dõi/accepted risk, không tách P0.
- *Tác động business (SLO/BUDGET/INCIDENT_HISTORY):*
  Valkey: không mất doanh thu trực tiếp (khách thêm lại giỏ được) nhưng ảnh hưởng trải nghiệm mỗi lần deploy/node event — **INC-2 là bằng chứng lịch sử đã đóng nhưng bài học còn treo ("vài thành phần vẫn là SPOF")**. Postgres/Kafka: rất cao nếu xảy ra, nhưng có thể trùng phạm vi mandate managed-DB sắp tới.
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

## REL-13 — 🟠 Grafana OOMKilled 11 lần/ngày — hiện tạm ổn định, nhưng gốc chưa vá (sẽ tái phát khi tải tăng)
*Trụ:* Reliability / Observability · *Ưu tiên đề xuất:* P0 · *Owner:* Chưa gán

- *Evidence:*
  `grafana-7779557549-c7tvr`: `Restart Count: 11` (tích luỹ, tăng dần trong ngày 09/07: 2 → 4 → 9 → 11 qua các lần kiểm tra), mỗi lần `Last State: OOMKilled`, `Exit Code: 137`. `memory limit: 300Mi` / `request: 250Mi` — **không đổi từ baseline, tức nguyên nhân gốc chưa được vá**. **Cập nhật hiện trạng (10/07): pod đang `Running`, `Ready: True`, OOM gần nhất `09/07 09:48 UTC` → đã ổn định ~17h, dashboard hiện DÙNG ĐƯỢC.** *(Quan trọng khi demo: đừng nói "Grafana đang chết" — nó đang chạy. Nói đúng: "đã OOM 11 lần trong ngày qua, hiện tạm ổn vì tải giảm, nhưng limit 300Mi chưa sửa nên sẽ tái phát khi tải tăng lại.")* Tương quan với Jaeger: 2 lần crash gần-đồng-thời trong ngày (19 giây và ~1 phút cách nhau) — nghi 1 nguyên nhân chung (traffic từ CloudFront, chưa xác nhận qua ingestion rate thật).
- *Ảnh hưởng khách hàng:*
  Không ảnh hưởng trực tiếp khách hàng (Grafana không nằm trên luồng mua hàng), nhưng nếu nó OOM lại **đúng lúc** có incident khác trên luồng checkout, team **mất khả năng quan sát đúng lúc cần nhất** — ảnh hưởng gián tiếp tới tốc độ phản ứng mọi sự cố khác.
- *Rủi ro (khả năng × mức nghiêm trọng):*
  Khả năng cao (đã xảy ra thật 11 lần, gốc chưa vá → chắc chắn tái phát khi tải tăng, chỉ là chưa biết khi nào) × nghiêm trọng cao (mù quan sát đúng lúc cần) = **P0**. *Không hạ xuống P1 dù hiện tạm ổn — vì "tạm ổn do tải thấp" không phải là đã vá.*
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
  Toàn bộ REL-13, REL-14, REL-16 và các warning readiness đều bị phát hiện **thủ công** qua `describe`/`events`, không qua alert nào. `kubectl get pdb -A` chỉ thấy PDB cho `coredns`/`opensearch-pdb`. Ví dụ sống: Grafana OOM 11 lần và Kafka OOM (REL-16) trong ngày qua — **không có alert nào bắn**, chỉ phát hiện được nhờ chủ động chạy `kubectl get pods` soi cột RESTARTS; nếu không ai soi tay đúng lúc thì không ai biết.
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

## REL-16 — 🔴 Kafka OOMKilled thật (10/07 sáng) — near-miss thật cho REL-09/REL-10, không còn là rủi ro lý thuyết
*Trụ:* Reliability · *Ưu tiên đề xuất:* P0 · *Owner:* Chưa gán

- *Evidence:*
  Verify trực tiếp sáng 10/07 (~08:36 ICT): pod `kafka-776b98df67-sv54c` — `Last State: OOMKilled`, `Exit Code: 137`, `memory limit: 700Mi` / `request: 700Mi` (QoS Guaranteed). Chạy ổn định **~21.5 giờ liên tục** (`Started: Thu 09 Jul 10:48:24` → `Finished: Fri 10 Jul 08:16:20`) trước khi OOM — không phải crash ngay lúc khởi động như REL-14, mà là **memory tăng dần theo thời gian rồi tràn** (pattern khác hẳn, gợi ý leak hoặc thiếu cấu hình retention/cleanup cho broker). Restart lúc `08:16:21`, quan sát lúc `08:36` đã lên lại `Running` bình thường, `Restart Count: 1`.
- *Ảnh hưởng khách hàng:*
  Nếu đúng lúc OOM có đơn hàng đang nằm trong topic `orders` chưa được `accounting`/`fraud-detection` consume kịp — **đơn đó mất vĩnh viễn, không có cách nào truy lại**, trong khi khách đã có thể bị charge tiền (qua `payment`) trước đó trong luồng `checkout`.
- *Rủi ro (khả năng × mức nghiêm trọng):*
  Khả năng đã xảy ra thật (không phải giả định) × nghiêm trọng rất cao (đúng kịch bản tệ nhất mà REL-09 mô tả, cộng thêm mất dữ liệu vĩnh viễn vì REL-10) = **P0**.
- *Tác động business (SLO/BUDGET/INCIDENT_HISTORY):*
  Đây là **bằng chứng sống (near-miss)** biến 2 rủi ro lý thuyết đã ghi (REL-09: fire-and-forget ack + auto-commit sớm; REL-10: Kafka không có PVC) thành 1 sự cố suýt xảy ra thật trong ngày — nâng độ khẩn cấp của cả 2 mục đó lên đáng kể, không chỉ của riêng REL-16.
- *Giải pháp đề xuất:*
  Ngắn hạn: tăng `kafka.resources.limits.memory` (hiện 700Mi) có kiểm soát, đo theo pattern tăng dần trong ~21h qua Grafana (nếu có số liệu Prometheus lưu lại) thay vì đoán số mới. Trung hạn: kiểm tra cấu hình retention/log segment cleanup của KRaft broker (`log.retention.*`, `log.segment.bytes`) — nghi đây là nguyên nhân memory tăng dần chứ không phải traffic đột biến. Phụ thuộc REL-09 (đổi ack + manual commit) để giảm thiệt hại nếu OOM tái diễn trước khi vá được nguyên nhân gốc.
- *Chi phí / effort:*
  Thấp cho việc tăng memory tạm thời (~15 phút). Trung bình cho điều tra cấu hình retention (~1-2 giờ, cần đọc kỹ Kafka broker config trong `values.yaml`).
- *Acceptance criteria:*
  Kafka chạy ổn định ≥48 giờ không OOM sau khi điều chỉnh; nếu vẫn OOM, có số liệu Prometheus xác nhận pattern tăng dần để loại trừ nguyên nhân traffic đột biến.
- *Rollback / nếu làm sai:*
  `helm upgrade` trả memory limit về 700Mi. Phát hiện qua `kubectl get pods` restart count tăng — vài phút. **Lưu ý:** mỗi lần Kafka pod restart (kể cả do rollback) vẫn mất toàn bộ message đang lưu (chưa vá REL-10) — cân nhắc thời điểm ít traffic nếu phải restart thủ công.

## REL-17 — Thay/bổ sung SSM bastion bằng access theo SSO (đề xuất: Cloudflare Zero Trust)
*Trụ:* Reliability / Operational Excellence (liên quan Security — cần phối hợp CDO01) · *Ưu tiên đề xuất:* P2 · *Owner:* Chưa gán

- *Evidence:*
  Xác nhận thật trong lúc vận hành 14/07 (không phải suy đoán): tunnel `aws ssm start-session --document-name AWS-StartPortForwardingSessionToRemoteHost` tự đóng sau ~10-20 phút idle, phải dò lại `bastion_instance_id`/`cluster_endpoint` qua `terraform output` và chạy lại lệnh full tham số mỗi lần cần `kubectl`. Không có cơ chế giữ phiên hay tự reconnect. Ngoài ra danh tính vẫn là **IAM user tĩnh**, không qua SSO — khớp đúng rủi ro đã ghi trong `CLAUDE.md` mục "Rủi ro chưa xử lý": cả 4 IAM user (`arthur`, `CDO01`, `CDO02`, `AIO02`) + `mentor` đều `AdministratorAccess`, trái nguyên tắc least-privilege đang áp dụng ở IRSA/ECR CI role.
- *Ảnh hưởng khách hàng:*
  Không trực tiếp — đây là công cụ vận hành nội bộ, không phải đường traffic khách hàng. Ảnh hưởng gián tiếp: mỗi lần tunnel chết giữa lúc xử lý sự cố làm chậm MTTR (mất vài phút dựng lại tunnel đúng lúc cần phản ứng nhanh).
- *Rủi ro (khả năng × mức nghiêm trọng):*
  Khả năng cao (đã xảy ra lặp lại nhiều lần trong 1 phiên làm việc) × nghiêm trọng trung bình (làm chậm thao tác, không gây outage trực tiếp, nhưng cộng dồn với rủi ro `AdministratorAccess` sprawl đã biết) = **P2**.
- *Tác động business (SLO/BUDGET/INCIDENT_HISTORY):*
  Không đụng SLO khách hàng trực tiếp, nhưng thuộc đúng trụ Operational Excellence (RULES.md mục 4) và góp phần đóng rủi ro Security đã tự gắn cờ — hội đồng nhiều khả năng hỏi tới vì đã ghi rõ trong CLAUDE.md là "chưa xử lý".
- *Giải pháp đề xuất:*
  Đánh giá 4 lựa chọn thị trường (SSM bastion hiện tại / OpenVPN / Tailscale / NetBird / **Cloudflare Zero Trust**) trên 3 tiêu chí: ops overhead, bề mặt lộ ra (inbound port), và mô hình cấp quyền. Khuyến nghị **Cloudflare Zero Trust** (`cloudflared` tunnel, outbound-only, giữ nguyên posture 0 inbound port như SSM hiện tại) + Access policy theo SSO/MFA — giải quyết đồng thời cả 2 vấn đề: (1) hết cảnh tunnel chết giữa chừng (Access session theo policy, không phải port-forward tay per-session), (2) thay dần IAM user tĩnh bằng danh tính SSO có thể revoke/audit theo từng người, thu hẹp trực tiếp bề mặt `AdministratorAccess` sprawl. Cấp quyền theo từng app (ai vào Grafana, ai vào kubectl-proxy...) thay vì mesh VPN kiểu Tailscale/NetBird (vào 1 node coi như vào cả mạng trừ khi tự cấu hình ACL kỹ) — khớp least-privilege hơn. Loại OpenVPN vì tự quản PKI/revoke cert là thêm việc, ngược hướng đang cần giảm ops overhead.
- *Chi phí / effort:*
  Free tier Cloudflare Zero Trust đủ cho quy mô team (≤50 user). Effort trung bình: cần tài khoản Cloudflare (BTC/CDO02 tự tạo, ngoài phạm vi Claude Code có thể tự làm — tạo tài khoản/nhập thông tin xác thực nằm trong danh sách hành động cấm), liên kết SSO (Google Workspace hoặc GitHub org hiện có), dựng `cloudflared` như 1 Deployment nhỏ trong cluster (outbound tunnel tới Cloudflare edge), viết Access policy cho từng app (kubectl-proxy, Grafana, ArgoCD). Không cần đổi domain hiện có — Access có sẵn domain miễn phí dạng `<team>.cloudflareaccess.com`.
- *Acceptance criteria:*
  Truy cập `kubectl`/Grafana/ArgoCD qua Cloudflare Access thành công với SSO, không cần lệnh `aws ssm start-session` tay nữa; audit log Access ghi được đúng người/thời điểm truy cập; SSM bastion giữ lại làm fallback cho tới khi migration verify ổn định qua ≥1 tuần vận hành thật (không tắt ngay).
- *Rollback / nếu làm sai:*
  Đây là bổ sung song song, không thay thế ngay — SSM bastion giữ nguyên hoạt động trong suốt quá trình đánh giá/triển khai thử. Nếu Cloudflare Access gây vấn đề (không vào được, chi phí phát sinh ngoài dự kiến), gỡ `cloudflared` Deployment + Access app, quay lại 100% SSM bastion — không có state nào bị khoá vào Cloudflare (EKS API vẫn private-only, không đổi cấu hình mạng cluster).

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
  Trực tiếp vào ngân sách $300/tuần. 3 node t3.large ≈ $53/tuần (line compute lớn nhất). Autoscaler scale-down 1–2 node lúc tải thấp (ban đêm gần như 0 traffic) tiết kiệm **ước tính ~$18–35/tuần** — giữ tối thiểu 1–2 node cho baseline, không scale về 0. *(Không claim tiết kiệm $42 như bản nháp cũ — số đó ngụ ý scale-down gần hết 3 node, không an toàn và không nhất quán với $53 tổng.)*
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

## COST-05 — ⚠️ Đính chính: `load-generator` đã OOMKilled thật ở 1500Mi — KHÔNG giảm, cần điều tra trước
*Trụ:* Cost Optimization / Reliability · *Ưu tiên đề xuất:* P2 (giữ nguyên mức, nhưng đổi hướng giải pháp) · *Owner:* Chưa gán

- *Evidence:*
  `load-generator` được cấp 1500Mi memory — ban đầu đánh giá là "cao bất thường" (~17% tổng memory limit cộng dồn). **Cập nhật 10/07 tối (verify lại qua `kubectl describe`):** pod đã **OOMKilled thật** (`Exit Code 137`, `Restart Count: 2`, lần gần nhất cách đây ~11 giờ tính tới lúc kiểm tra, chạy được ~18 giờ trước khi OOM) — nghĩa là 1500Mi **không hề dư, thậm chí có thể không đủ** dưới tải nhất định. Kết luận ban đầu (COST-05 gốc) **sai hướng**.
- *Ảnh hưởng khách hàng:*
  Không ảnh hưởng trực tiếp (bot giả lập traffic, không phục vụ khách thật) — nhưng nếu `load-generator` chết giữa lúc đang tạo tải cho 1 bài test/demo (VD lúc Pitch), kết quả benchmark sẽ sai lệch.
- *Rủi ro (khả năng × mức nghiêm trọng):*
  Khả năng đã xảy ra thật (không còn giả định) × nghiêm trọng thấp (không đụng khách hàng) = **P2**, nhưng **đổi hẳn hướng giải pháp** — không được tự ý giảm limit nữa.
- *Tác động business (SLO/BUDGET/INCIDENT_HISTORY):*
  Thấp trực tiếp, nhưng rủi ro làm sai số liệu P08 (baseline load test CDO01 đang chuẩn bị làm) nếu load-generator tự chết giữa chừng không ai để ý.
- *Giải pháp đề xuất:*
  **KHÔNG giảm memory limit như đề xuất ban đầu.** Trước tiên điều tra nguyên nhân OOM thật (có thể liên quan `LOCUST_USERS` đặt quá cao, hoặc leak tương tự Kafka ở REL-16) qua log `--previous`; chỉ xem xét tăng/giảm sau khi có dữ liệu, không đoán theo tỉ lệ % memory cộng dồn như cách đánh giá cũ.
- *Chi phí / effort:*
  Thấp — điều tra log trước (~30-45 phút), chưa nên đổi config vội.
- *Acceptance criteria:*
  Xác định được nguyên nhân OOM cụ thể (config `LOCUST_USERS` hay leak); `load-generator` chạy ổn định ≥24h không OOM sau khi áp fix đúng nguyên nhân (không phải chỉ đổi số ngẫu nhiên).
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

**Đã đổi sang bám sát đúng mục 4 của Meeting note liên team (09/07)** — thứ tự này là thứ tự chung cả 3 team thống nhất, không phải chỉ riêng CDO02 tự xếp nữa. Ghi theo mã P chung, kèm mã CDO02 và owner để biết phần nào CDO02 trực tiếp làm.

0. **(Mới, 10/07 sáng, sau meeting — chưa có mã P chung, đề xuất P26 tạm)** **REL-16** — Kafka OOMKilled thật, near-miss cho P05/P06 (xem chi tiết REL-16 ở trên). *CDO02 chủ trì, cần báo ngay cho CDO01/AI Ops vì đây là bằng chứng sống làm tăng độ khẩn cấp của P05/P06 — nên xin gắn mã P chung trong meeting tiếp theo thay vì để CDO02 tự đặt số.*
1. **P01 + P02** (REL-02 + REL-03) — sửa health check thật + thêm probe. *CDO02 chủ trì P01, phối hợp CDO01 ở P02.*
2. **P03** (REL-01) — tăng replicas checkout path. *CDO02 phối hợp CDO01.*
3. **P04 + P05 + P06** (REL-04 + REL-09) — rollback checkout, sửa accounting/Kafka mất đơn âm thầm. *CDO02 chủ trì cả 3, không cần CDO01. **Cập nhật 10/07:** REL-16 (Kafka OOM thật) vừa chứng minh rủi ro P05/P06 xảy ra thật trong ngày, không còn lý thuyết — nên nêu bằng chứng này khi bảo vệ độ ưu tiên.*
4. **P07 + P08** (metrics-server, baseline load test/RED) — *CDO01 chủ trì, CDO02 không cần tự làm (đã bàn giao qua meeting).*
5. **P09 + P10** (REL-13 + REL-15) — sửa Grafana/Jaeger OOM + thêm alert. *CDO02 phối hợp CDO01. P09: Grafana/Jaeger đã OOM 11/7 lần hôm qua, hiện tạm ổn định (~17h) nhưng limit chưa vá → sẽ tái phát khi tải tăng (xem REL-13, đừng nói "đang chết" khi demo vì dashboard hiện chạy được).*
6. **P15 + P16** (NetworkPolicy + ingress boundary) — *CDO01 chủ trì. CDO02 cần theo sát P16 vì đụng trực tiếp `infra/cloudfront.tf` mình vừa dựng.*
7. **P11 + P12 + P22** (HPA, CPU requests/limits, Cluster Autoscaler/Karpenter) — *CDO01 chủ trì hoàn toàn, không còn là việc CDO02 (meeting đã chuyển giao).*

**Phần CDO02 tự làm thêm, ngoài phạm vi P01-P25 (không có mã P chung):**
- **P1 nội bộ:** REL-05 (P13), REL-10 phần Valkey (P14) — đã có mã P, thứ tự nằm trong bước 3-4 ở trên theo phụ thuộc riêng (REL-05 phụ thuộc REL-01/02/03 xong trước).
- **P2 nội bộ (khi còn thời gian):** COST-01 (ECR lifecycle), COST-03 (Spot), COST-04 (right-size), COST-05 (điều tra OOM load-generator — **không phải giảm memory**, xem đính chính ở COST-05), REL-11 (currency validate), REL-12 (quote validate).

**Theo dõi, không chủ động làm:** REL-08 (và phần Postgres/Kafka trong REL-10) — chờ mandate BTC. Không có mã P tương ứng trong meeting, đúng như đánh giá ban đầu — không ai trong 3 team yêu cầu làm sớm.

**Đã hoàn thành, nêu để ghi công:** COST-07 (NAT Gateway đơn).

---

## OPERATIONAL EXCELLENCE — Việc đã hoàn thành tuần 1 (07/07 - 10/07)

Ghi lại theo đúng tinh thần RULES.md mục 4 ("Operational Excellence — xương sống Phase 3, vận hành hướng tới kết quả kinh doanh") và dùng cho Ops Review hằng tuần. Đây là **việc đã làm xong**, không phải backlog còn mở — mỗi mục kèm commit thật để truy vết (đúng nguyên tắc Auditability: mọi quyết định phải truy được về người).

### 1. Hạ tầng nền + CI/CD (tự động hóa, giảm thao tác tay)

- **Dựng baseline VPC + EKS bằng Terraform** từ đầu — 1 VPC/3AZ, 1 NAT Gateway (cost-conscious ngay từ đầu, xem COST-07), EKS managed node group. (`2474d2e infra: add Terraform for VPC + EKS baseline`, `d7a4f76 chore: commit terraform lockfile`)
- **Chuyển EKS API sang private-only + dựng SSM bastion** làm đường vào duy nhất — xử lý dứt điểm sự cố bị đè mất IP allowlist 2 lần trước đó, viết hướng dẫn truy cập đầy đủ cho cả team. (`4db2961 infra: SSM bastion, EKS API now private-only`, `44c64d5 docs: full SSM bastion access guide for the team`)
- **Dựng CloudFront trước `frontend-proxy` + CI/CD Terraform tự động** (`terraform-plan.yml` chạy trên mọi PR, `terraform-apply.yml` gate bằng `production` environment cần approve tay) — không còn ai `terraform apply` tay từ máy cá nhân nữa. (`17e99f6 infra: CloudFront in front of frontend-proxy + Terraform plan/apply CI`)
- **Vá lỗi CI OIDC trust condition** — role apply không nhận đúng `sub` claim khi job dùng GitHub Environment, chặn hẳn pipeline apply cho tới khi sửa. (`6e61f98 fix(ci): terraform-apply OIDC role trust condition didn't match the "production" environment sub claim`)
- **Secret-scanning (gitleaks)**: dựng pre-commit hook + GitHub Actions gate trên mọi PR/push vào `main`, sửa 2 lỗi cấu hình (RE2 regex không hợp lệ, thiếu `GITHUB_TOKEN` cho action), xử lý đúng quy trình 2 lần false-positive (không phải secret thật, verify qua log CI trước khi allowlist — không đoán). (`e53c38a`, `15a93fe`, `dbb36a8`, `0ba5f72`)

### 2. Sự cố đã xử lý (Incident response)

- **`accounting` OOMKilled 44 lần/19h** — xác định nguyên nhân (memory limit 120Mi quá thấp), vá lên 350Mi, verify ổn định (0 restart sau vá), viết postmortem đầy đủ và đóng chính thức. (`ca0039e docs: postmortem - accounting OOMKilled + ECR lifecycle self-incident`, `a44e527 docs: mark postmortem 0001 as closed - verified fix`)
- Trong cùng postmortem: ghi nhận + xử lý sự cố ECR lifecycle policy tự gây ra (đã xóa sai, đang chờ viết lại đúng cách — COST-01).

### 3. Backlog ưu tiên CDO02 — dựng, đào sâu, và verify liên tục (không chỉ viết 1 lần)

- **Dựng backlog CDO02 ban đầu** (17 mục Reliability/Cost đầu tiên, xếp hạng theo công thức Rủi ro × Tác động business). (`a4008bf docs: CDO02 backlog - Reliability + Cost Optimization`)
- **Đọc sâu code toàn bộ ~18 service** (không dừng ở đọc `values.yaml`), phát hiện thêm 4 lỗ hổng chưa từng thấy: Kafka fire-and-forget + accounting auto-commit sớm (mất đơn hàng âm thầm), Valkey không persistence, currency chia-cho-0 âm thầm, quote nuốt exception. (`49a1ff3 docs: deep code-read findings R9-R12`)
- **Verify runtime độc lập nhiều lần trong 2 ngày** (không chỉ tin vào báo cáo người khác) — đối chiếu evidence của phucdo, tự kiểm tra lại bằng `kubectl describe`/CloudWatch audit log, phát hiện Grafana/Jaeger OOM đang **active thật** (không phải lịch sử), sau đó phát hiện thêm Kafka OOM (REL-16, near-miss thật cho rủi ro mất đơn hàng). (`03a1525`, `0f7c632`, `f8f4a90`, `6903758`)
- **Xác nhận ai chạy lệnh gây lỗi** qua CloudTrail/EKS audit log khi cần (không phỏng đoán) — tra được chính xác user, thời điểm, lý do fail của 1 lần `helm upgrade` thử vá Grafana không thành công.
- **Rewrite toàn bộ backlog sang format RCA chuẩn** (Evidence / Ảnh hưởng khách hàng / Rủi ro / Tác động business / Giải pháp / Chi phí / Acceptance criteria / Rollback cho từng mục) và **đối chiếu với backlog chung `P01-P25`** chốt trong meeting liên team AI + CDO01 + CDO02 — rõ mục nào CDO02 chủ trì, mục nào đã bàn giao CDO01. (`4986c68 docs: rewrite backlog to full RCA format + reconcile with joint AI/CDO01/CDO02 meeting`)
- **Hardening backlog trước Pitch** — thay số liệu định tính bằng bằng chứng đo được thật (SLO checkout breach truy được về nguyên nhân cụ thể: node rolling-replace K8s 1.31→1.32), sửa lại 1 chỗ gán nhầm incident (INC-2 thực ra map với REL-10 - mất giỏ hàng, không phải REL-01), đồng bộ lại COST-02/COST-05 sau khi có bằng chứng mới, sửa nhầm ngày họp. (`3da92f5`, `76ddf07`, `6688923`, `cf417f5`, `982c1dd`)

### 4. Duy trì continuity — để không ai phải giải thích lại từ đầu

- **`CLAUDE.md`** — tạo và cập nhật liên tục trong tuần để bất kỳ phiên làm việc mới nào (kể cả người khác, kể cả AI) đọc là hiểu ngay trạng thái thật, không cần hỏi lại. (`191d5c1`, `a01bad4`, `bd91582`)
- **Kịch bản Pitch riêng** (`PITCH-CDO02.local.md`, không commit vào repo chung — đúng quy tắc file cá nhân/team-private) kèm rule `.gitignore` cho `*.local.md` để tránh rò rỉ note nội bộ chưa sẵn sàng chia sẻ. (`5aa5164 chore: gitignore *.local.md`)

**Điểm nhấn khi báo cáo Ops Review:** tuần này không chỉ "tìm ra vấn đề" mà còn **tự động hóa được phần lớn thao tác tay dễ gây lỗi nhất** (Terraform apply, image build/push, secret scanning) — trực tiếp giảm rủi ro loại lỗi đã từng xảy ra thật (allowlist bị đè, helm upgrade gõ sai tay). Backlog Reliability/Cost cố ý **chưa code** theo đúng tinh thần "tuần 1 là tuần find + note", nhưng hạ tầng vận hành (Operational Excellence) thì đã có kết quả cụ thể, đo được.
