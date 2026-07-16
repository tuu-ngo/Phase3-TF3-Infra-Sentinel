# Mandate #8 — Kế hoạch thực thi migrate 3 datastore lên managed

**Người làm & chịu trách nhiệm:** Huu Tai Ngo (CDO02 — Reliability + Cost Optimization)
**Ngày lập:** 16/07/2026 · **Hạn mandate:** hết ngày 20/07/2026
**Cơ sở kỹ thuật:** [ADR 0009](adr/0009-mandate-08-managed-migration-cdo02.md) (quyết định + đánh đổi)
· [Runbook cutover](runbooks/mandate-08-managed-cutover.md) (lệnh từng bước)
**Phạm vi file này:** lịch thực thi 4 ngày + kết quả re-verify hệ thống + điều kiện dừng/lùi.
Không lặp lại lập luận của ADR — chỉ tham chiếu.

---

## 1. Re-verify hệ thống trước thực thi (đo trực tiếp 16/07/2026, ~21:00 +07)

Mọi giả định nền của ADR 0009 được kiểm lại trên cluster + AWS thật trước khi bắt đầu.
**Kết luận: tất cả giả định đứng vững.** Hai số liệu cập nhật (dữ liệu lớn hơn lúc viết ADR — không đổi kết luận nào).

### 1.1 Version khớp managed 1:1 — xác nhận cả hai phía

| Store | In-cluster (đo 16/07) | Managed khả dụng ap-southeast-1 (API 16/07) | Khớp |
|---|---|---|---|
| PostgreSQL | `17.6` (Debian), extension chỉ `plpgsql`, `wal_level=replica` | RDS `17.6` | ✅ |
| Valkey | `9.0.1`, AOF `yes` | ElastiCache Valkey `9.0` | ✅ |
| Kafka | `3.9.1`, KRaft (`process.roles=controller,broker`) | MSK `3.9.x.kraft` | ✅ |

### 1.2 Điều kiện của chứng minh zero-loss (ADR §5) — xác nhận từng cái

| Điều kiện | Đo được 16/07 | Trạng thái |
|---|---|---|
| `accounting` là **người ghi PG duy nhất** | Source: chỉ `accounting/Consumer.cs:133-163` có `Add`+`SaveChanges`; `product-catalog` 0 câu ghi; `product-reviews/database.py` chỉ `SELECT`. Live `pg_stat_activity`: đúng 5 client = accounting ×1 + product-catalog ×2 + product-reviews ×2, không có kẻ lạ | ✅ |
| `accounting` offset thủ công (replay được) | `Consumer.cs:187 EnableAutoCommit=false`; consumer group `accounting` trên broker: offset commit, **lag=0** | ✅ |
| Cart TTL 60 phút mọi lần ghi | `ValkeyCartStore.cs:174,199` — `KeyExpireAsync(60min)` ở cả `AddItem`/`EmptyCart`; mẫu 5 key live đều có TTL (365s–3324s) | ✅ |
| `checkout` publish đồng bộ `acks=all` | `checkout/kafka/producer.go:46 RequiredAcks=WaitForAll`, `SyncProducer` | ✅ (→ MSK phải RF=3/min.insync=2) |
| Retention topic `orders` ≫ cửa sổ cutover | Không override topic-level lẫn broker config → default **168h**; consumer groups: `accounting` lag 0, `fraud-detection` lag 1 | ✅ |
| VPC đủ cho Multi-AZ private | `vpc-0c0b86b42bbbefd55`: 3 private subnet đúng 3 AZ (1a `10.0.0.0/20`, 1b `10.0.16.0/20`, 1c `10.0.32.0/20`) | ✅ |
| External Secrets Operator sẵn sàng | namespace `external-secrets`: 3 pod Running (controller + cert + webhook) | ✅ |
| Load-generator cho tải nền lúc cutover | deploy `load-generator` 1/1 Running | ✅ |

### 1.3 Số liệu cập nhật so với ADR (dữ liệu đã lớn hơn — kết luận không đổi)

| Mục | ADR (16/07 sáng) | Đo lại (16/07 tối) | Ảnh hưởng |
|---|---|---|---|
| PG size | 29 MB | **38 MB** | dump/restore vẫn vài giây |
| `accounting.order` / `orderitem` / `shipping` | 29k / 53k / — | **40.987 / 75.059 / 40.987** | dùng số MỚI làm mốc parity |
| Valkey keys | 864 | **4.162** | dual-write 60' không đổi |
| Topic `orders` | — | **1 partition**, offset ~35.692 | tạo topic MSK 1 partition (giữ ordering), RF=3 |

### 1.4 Trạng thái store cũ (đường lui — giữ nguyên tới nghiệm thu)

Pod: `postgresql` / `valkey-cart` / `kafka` đều 1/1 Running; PVC: `postgresql-data` 2Gi /
`valkey-cart` 1Gi / `kafka-data` 3Gi đều Bound (gp2).

## 2. Lịch thực thi 4 ngày

Nguyên tắc xếp lịch: **2 điểm nghẽn quyết định thứ tự** — (a) MSK provision 30–60+ phút → Terraform
đi trước tất cả; (b) 4 service phải rebuild image qua pipeline CI **vừa đổi** (PR #153/#158/#159)
→ build sớm để còn giờ sửa nếu pipeline trục trặc.

### Ngày 0 — tối 16/07: hạ tầng lên trước

| # | Việc | Ghi chú |
|---|---|---|
| 0.1 | Terraform module `datastores`: RDS (Multi-AZ, PG 17.6, `db.t4g.micro`, gp3 20GB) + ElastiCache (Valkey 9.0, `cache.t4g.micro` ×2, auth-token, TLS) + MSK (3× `kafka.t3.small`, 3 AZ, `3.9.x.kraft`, SASL/SCRAM) + KMS CMK + 3 secret (`techx-tf3/postgres`, `techx-tf3/elasticache-auth`, `AmazonMSK_techx-tf3/kafka-scram`) + SG (inbound chỉ từ SG node group; RDS/ElastiCache thêm SG bastion) | `plan -out=tfplan` → review → `apply tfplan`. Encryption at rest cả 3. `PubliclyAccessible=false` |
| 0.2 | Close PR #151 (nội dung đã lên `main` dưới số ADR 0009 — tránh merge trùng) | |

### Ngày 1 — 17/07: code + secret, deploy với cờ TẮT

| # | Việc | Ghi chú |
|---|---|---|
| 1.1 | `checkout`: SCRAM client cho sarama (`xdg-go/scram`) + env `KAFKA_SECURITY_PROTOCOL`/`KAFKA_SASL_*` — **làm đầu tiên, nặng nhất** | default `PLAINTEXT` = hành vi cũ |
| 1.2 | `cart`: env `VALKEY_TLS` + `VALKEY_AUTH_TOKEN` + **nhánh dual-write** `VALKEY_DUAL_WRITE_ADDR` (rỗng = tắt) | 3 việc trong 1 PR |
| 1.3 | `accounting` + `fraud-detection`: `SecurityProtocol` qua env | mỗi cái vài dòng config |
| 1.4 | ExternalSecret: render 3 format conn string PG (.NET / Go-URL / libpq) + token + SCRAM; `batch-associate-scram-secret` gắn secret vào MSK; **gỡ `otelu/otelp` khỏi `values.yaml`** | ⚠️ update `values.schema.json` cùng lúc + verify `helm template` trước commit (bài học ComparisonError) |
| 1.5 | Build 4 image qua CI (digest-pinned, `imageOverride` ghi FULL `<sha>-<service>`) → deploy cờ tắt → verify hành vi y nguyên (checkout vẫn đặt hàng OK, cart vẫn hoạt động) | qua PR → main → ArgoCD |

**Gate cuối ngày 1:** 3 store managed `available` + 4 service chạy image mới hành vi không đổi + secret sync vào cluster. Chưa đạt → ngày 2 KHÔNG cutover.

### Ngày 2 — 18/07: cutover Valkey (dễ nhất — kiểm chứng toàn đường ống)

| # | Việc | Verify |
|---|---|---|
| 2.1 | Seed schema PG sang RDS trước (`pg_dump --schema-only` + seed `catalog`/`reviews` tĩnh) — chuẩn bị cho ngày 3, không đụng app | so schema RDS = PG cũ |
| 2.2 | Bật dual-write `cart` (ghi cũ + ElastiCache, đọc từ cũ) | hành vi khách không đổi |
| 2.3 | **Chờ ≥ 65–70 phút** (cửa sổ TTL 60' + biên — BẮT BUỘC, rút ngắn = phá chứng minh) | key count ElastiCache hội tụ về ~key count cũ |
| 2.4 | Lật đọc sang ElastiCache (`VALKEY_ADDR` + `VALKEY_TLS=true`), **giữ dual-write** | SLO cart/browse trên Grafana; thêm/xoá giỏ e2e qua storefront |
| 2.5 | Giữ pod `valkey-cart` cũ nguyên | rollback = trả env, ~1 phút |

### Ngày 3 — 19/07: cutover Postgres rồi Kafka (giờ ít traffic, load-gen nền chạy, Grafana SLO mở suốt)

**Postgres (đóng băng người ghi duy nhất):**

| # | Việc | Verify |
|---|---|---|
| 3.1 | **Re-audit lần cuối** `accounting` vẫn là writer duy nhất (nếu code đổi từ 16/07 → dừng, audit lại) | `pg_stat_activity` + git log src |
| 3.2 | Scale `accounting` → 0. Khách không ảnh hưởng (reader vẫn đọc; checkout vẫn publish Kafka) | storefront browse/checkout OK |
| 3.3 | `pg_dump` → restore RDS (38 MB) | — |
| 3.4 | **Parity trên nguồn đóng băng**: row count + checksum 5 bảng (`order` 40.987+Δ, `orderitem` 75.059+Δ, `shipping` 40.987+Δ, `products` 10, `productreviews` 50 — số chốt lúc freeze) | khớp TUYỆT ĐỐI mới đi tiếp |
| 3.5 | Đổi `DB_CONNECTION_STRING` 3 service → RDS (`sslmode=require`), rolling `maxUnavailable:0` | 0 rớt request (Grafana) |
| 3.6 | Scale `accounting` → 1, trỏ RDS → replay đơn dồn từ offset chưa commit | lag `accounting` → 0; đếm `order` RDS tăng đúng số đơn dồn |

**Kafka (producer-first — THỨ TỰ LÀ SỐNG CÒN):**

| # | Việc | Verify |
|---|---|---|
| 3.7 | Tạo topic `orders` trên MSK: **1 partition** (giữ ordering hiện tại), RF=3, min.insync=2 | — |
| 3.8 | Chuyển `checkout` → MSK (`SASL_SSL`, cổng 9096 SCRAM) | đặt hàng e2e OK |
| 3.9 | ⚠️ **Chờ MỌI pod checkout lên revision mới** (`kubectl rollout status` + đếm pod revision cũ = 0) — đo lag khi còn pod cũ = nguy cơ message mồ côi | `rollout status` xong |
| 3.10 | Chờ lag Kafka cũ = 0 (cả `accounting` lẫn `fraud-detection`) | `kafka-consumer-groups --describe` |
| 3.11 | Chuyển 2 consumer → MSK, group mới + `AutoOffsetReset=Earliest` → nuốt trọn backlog từ 3.8 | tổng offset MSK + lag = khớp số đơn; đơn mới vào RDS |

### Ngày 4 — 20/07: bằng chứng + nghiệm thu

| # | Việc |
|---|---|
| 4.1 | Gói bằng chứng: (a) `kubectl get pods` — app trỏ managed; (b) bảng parity trước/sau; (c) Grafana SLO checkout ≥99% suốt 3 cửa sổ cutover (kèm khung giờ); (d) `PubliclyAccessible=false` + test không nối được từ ngoài VPC (KHÔNG dùng nslookup làm bằng chứng); (e) TLS+auth on cả 3; (f) `values.yaml` không còn plaintext credential |
| 4.2 | Mentor nghiệm thu cả 3 |
| 4.3 | **Chỉ SAU nghiệm thu:** gỡ pod + PVC `postgresql`/`valkey-cart`/`kafka` (= điểm không quay lui) → chốt yêu cầu "không còn pod data tự host" |
| 4.4 | Cập nhật CLAUDE.md + backlog (REL-08 đóng) + báo cáo mandate |

**Buffer duy nhất:** tối 19/07. Nếu trượt tiến độ → ưu tiên giữ **Postgres** (durability giá trị nhất, theo ADR), Valkey đã xong từ ngày 2, Kafka dời nếu bắt buộc.

## 3. Điều kiện dừng / lùi (stop conditions)

- **Gate ngày 1 fail** (managed chưa `available` / image mới đổi hành vi / secret không sync) → dời cutover, không dồn ép.
- **Parity 3.4 lệch dù chỉ 1 dòng** → dừng, scale `accounting` → 1 trỏ PG cũ (mất 0 vì replay), điều tra rồi làm lại.
- **SLO checkout chạm 99% trong bất kỳ cửa sổ nào** → rollback store đang cutover ngay (bảng rollback ADR §Rollback — mỗi store lùi độc lập ~1-2 phút bằng env, không rebuild image).
- **Bất kỳ bước nào lệch runbook** → dừng lại hỏi, không improvise trên luồng ra tiền.
- Sự cố BTC bơm giữa chừng (flagd) → xử lý sự cố trước theo nguyên tắc fallback/containment, cutover dời; **tuyệt đối không đụng flagd** để "dọn đường".

## 4. Ràng buộc tôn trọng (đối chiếu directive)

- **Ngân sách:** +$202.16/mo ≈ $46.7/tuần (đơn giá verify qua Pricing API — chi tiết ADR §Cost); tổng ước ≈ $147/tuần < trần $300/tuần.
- **Directive #1:** storefront public không đổi; 3 store private subnet, không public endpoint; SG mở tối thiểu.
- **Luật flagd:** không đụng ở bất kỳ bước nào.
- **GitOps:** mọi thay đổi app/values qua PR → `main` → ArgoCD (patch tay bị selfHeal revert); Terraform `plan -out` → `apply tfplan`, không auto-approve.

---
*Người lập & thực thi: **Huu Tai Ngo** — CDO02. Phối hợp: CDO01 (review SG/TLS/secret trước apply),
AIO02 (cập nhật detector theo dõi endpoint mới). Số liệu mục §1 đo trực tiếp trên cluster/AWS ngày 16/07/2026.*
