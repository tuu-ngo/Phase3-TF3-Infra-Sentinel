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

1. **R2 + R3** (sửa health check thật + thêm probe) — nền tảng, chi phí thấp, vá đúng INC-3.
2. **R1** (tăng replicas + PDB nhóm checkout) — tác động business cao nhất, chi phí thấp.
3. **R5** (connection pool) — vá đúng INC-1, chi phí thấp.
4. **R4** (rollback checkout) — rủi ro tài chính trực tiếp, chi phí thấp.
5. **R7** (CPU requests/limits) — nền tảng bắt buộc cho C2/C4.
6. **C1** (sửa lại lifecycle policy đúng cách) — dọn nợ tự gây ra.
7. **C2** (Cluster Autoscaler thật) — tiết kiệm chi phí đo được ngay.
8. **C6** (áp ResourceQuota) — làm sau R1+R7.
9. **C3** (Spot) — chỉ sau khi R1 xong.
10. **R6, C4, C5** — làm khi còn thời gian, giá trị thấp hơn nhóm trên.

**Cố ý bỏ ở Tuần 1:** R8 (migrate datastore) — chờ xem có thành mandate BTC không trước khi tự đầu tư công sức lớn.
