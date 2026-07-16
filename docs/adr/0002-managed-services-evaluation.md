# ADR 0002 — Đánh giá migrate datastore sang AWS managed service

**Ngày:** 12/07/2026
**Người quyết định:** CDO02 (Reliability + Cost Optimization)
**Trạng thái:** 🟡 Đã đánh giá — **quyết định có điều kiện** (làm RDS + ElastiCache nếu/khi
ưu tiên tới lượt; hoãn MSK). Chờ mandate BTC nếu có yêu cầu bắt buộc khác.
**Trụ liên quan:** Reliability (durability/HA) + Cost Optimization (ROI) + Operational Excellence

---

## Bối cảnh

3 datastore hiện chạy **in-cluster, 1 instance, 0 PVC** (xác minh runtime: `kubectl get
pv,pvc -A` → không có PV/PVC nào):
- **Postgres** — dùng chung bởi `product-catalog`, `product-reviews`, `accounting`.
- **Valkey** — giỏ hàng (`cart`).
- **Kafka** — 1 broker, luồng đơn hàng (`checkout` → `accounting`/`fraud-detection`).

Đây là gốc của **REL-08** (SPOF tầng dữ liệu) và **REL-10** (không persistence — restart
pod = mất dữ liệu). Câu hỏi: migrate sang managed service (RDS/ElastiCache/MSK) có phải
cách đúng để vá 2 rủi ro này không, và có nằm trong ngân sách không?

**Mốc ngân sách:** ~$300/tuần ≈ ~$1,200/tháng. Chi hiện tại phần lớn là 3× `t3.large`
on-demand (~$240/mo) + **EKS control plane đang extended support (~$500/mo, xem ADR 0001)**
+ NAT + ALB + CloudFront.

> ⚠️ Mọi số cost dưới đây là **ước tính cho ap-southeast-1**, cần verify bằng AWS Pricing
> Calculator trước khi cam kết. Dùng để so sánh tương đối, không phải hóa đơn.

## Phân tích từng datastore

### Postgres → RDS PostgreSQL — NÊN LÀM
- **Cải thiện:** vá cùng lúc REL-08 + REL-10 — Multi-AZ tự failover, backup tự động +
  point-in-time recovery, patch tự động. Đây là dữ liệu tài chính (đơn hàng/kế toán) —
  durability giá trị cao nhất.
- **Trade-off:** đắt hơn in-cluster; ít quyền tinh chỉnh sâu; cần migrate data (dump/
  restore, có downtime ngắn — cần lên kế hoạch cutover).
- **Cost ước tính:** `db.t3.micro` single-AZ ~$19/mo + storage ~$3/mo; **Multi-AZ ~$40-45/mo**
  (đáng tiền cho durability).

### Valkey → ElastiCache — NÊN LÀM (sau Postgres)
- **Cải thiện:** vá REL-10 phần giỏ hàng — hiện restart = mất sạch giỏ mọi khách.
  ElastiCache có replica + failover + snapshot.
- **Trade-off:** giỏ hàng là dữ liệu "mềm" (khách thêm lại được) → giá trị durability thấp
  hơn Postgres.
- **Cost ước tính:** `cache.t4g.micro` ~$12-16/mo (1 node); có replica ~gấp đôi.

### Kafka → MSK — HOÃN, không làm lúc này
- **Cải thiện:** vá REL-16 (Kafka OOM) + persistence + HA multi-broker.
- **Trade-off:** **MSK là cái đắt nhất.** Provisioned tối thiểu thực tế 2-3 broker +
  storage + data transfer; Serverless có phí base cao.
- **Cost ước tính:** MSK provisioned nhỏ nhất thực tế ~$100-150+/mo; MSK Serverless
  ~$540+/mo (base) — **vượt hẳn tỉ trọng hợp lý** của ngân sách $1,200/mo.
- **Thay thế rẻ hơn:** thêm PVC cho Kafka in-cluster + tăng memory (vá REL-16) — rẻ hơn
  nhiều lần, đủ dùng trong khung 3 tuần.

## Quyết định

| Datastore | Quyết định | Lý do |
|---|---|---|
| Postgres | **Migrate RDS (Multi-AZ)** khi tới lượt ưu tiên | ~$45/mo, vá REL-08+10, dữ liệu tài chính |
| Valkey | **Migrate ElastiCache** sau Postgres | ~$15/mo, vá REL-10 giỏ hàng |
| Kafka | **Giữ in-cluster** + PVC + tăng memory | MSK đắt gấp nhiều lần, ROI âm trong 3 tuần |

**Tổng thêm chi cho RDS + ElastiCache: ~$60/mo** — nằm gọn trong ngân sách, đặc biệt khi
nâng EKS thoát extended support (ADR 0001, tiết kiệm ~$400/mo) làm cùng lúc thì phần
migrate này gần như "miễn phí ròng".

## Điều kiện & ràng buộc
- **Nếu BTC ra mandate** migrate datastore theo cách khác (VD bắt buộc MSK, hay Aurora) →
  thực thi theo mandate, ADR này chỉ là đánh giá chủ động khi chưa có directive.
- Mỗi migration thật cần **kế hoạch cutover + rollback riêng** (dump/restore, đổi
  connection string qua secret, test trước) — sẽ ghi ADR con khi thực thi.
- Ưu tiên: **sau REL-01/02/03/09** (vá gốc reliability trước), không nhảy vào migrate khi
  luồng checkout còn chưa ổn định.

## Phương án đã cân nhắc và loại
- **Migrate cả 3 sang managed (gồm MSK):** loại — MSK phá ngân sách, ROI âm.
- **Tự dựng PVC + replication + backup cho cả 3 in-cluster:** tốn công vận hành hơn nhiều
  so với RDS/ElastiCache trả sẵn durability; chỉ giữ cách này cho Kafka (nơi managed quá đắt).
- **Không làm gì (giữ nguyên 0 PVC):** loại — REL-08/10 là rủi ro mất dữ liệu thật.

## Cơ hội managed khác (ghi nhận, ngoài phạm vi quyết định chính)
- **flagd token → AWS Secrets Manager** (~$0.40/secret/mo) — vá lỗ hổng token plaintext
  trong Helm release, rẻ, nên làm.
- **Karpenter** thay Cluster Autoscaler (COST-02) — scale node thông minh hơn, cùng chi phí.
- **Observability → AMP/AMG managed:** không nên — tốn thêm mà stack in-cluster đang chạy được.

---
*ADR này là bằng chứng tư duy cost-conscious có tính toán (không migrate bừa, không giữ
nguyên rủi ro) — dùng để trả lời hội đồng ở trụ Cost + Reliability.*
