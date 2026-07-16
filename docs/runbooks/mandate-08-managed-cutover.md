# Runbook — Mandate #8: cutover 3 store lên managed (RDS / ElastiCache / MSK)

Cơ sở kỹ thuật + đánh đổi: [ADR 0008](../adr/0008-mandate-08-managed-migration-cdo02.md).
Thứ tự: **Valkey → Postgres → Kafka** (dễ → khó). Mỗi store cutover **độc lập**, verify xong mới sang cái kế.

**Nguyên tắc xuyên suốt:**
- **KHÔNG xoá pod/PVC store cũ** cho tới khi mentor nghiệm thu cả 3. Store cũ = đường lui duy nhất.
- Giữ **tải nền thật** (load-generator ~20-50 user) suốt cutover — không có traffic thì "SLO không rớt" vô nghĩa.
- Mở **Grafana SLO dashboard** (https://grafana.arthur-ngo.org) suốt quá trình.
- Mọi thay đổi đi qua **PR → main → ArgoCD sync** (cluster là GitOps, patch tay bị selfHeal revert).

---

## 0. Chuẩn bị truy cập

```sh
export AWS_PROFILE=techx-new   # account 197826770971
aws ssm start-session --target i-02a8d3e39b87180ce \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters host="ADA05FFC84146C0AED730F78786EB320.gr7.ap-southeast-1.eks.amazonaws.com",portNumber="443",localPortNumber="8443" \
  --region ap-southeast-1
# terminal khác:
kubectl config set-cluster arn:aws:eks:ap-southeast-1:197826770971:cluster/techx-corp-tf3 \
  --server=https://localhost:8443 --insecure-skip-tls-verify=true
```

## 1. Pre-flight (làm 1 lần, TRƯỚC mọi cutover)

```sh
# a) Baseline SLO — ghi lại để so sánh
#    Grafana SLO dashboard: checkout success-rate, browse/cart, storefront p95

# b) Baseline data parity — CHỤP LẠI, đây là bằng chứng nộp
kubectl -n techx-tf3 exec deploy/postgresql -- psql -U otelu -d otel -t -c "
  SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY relname;"
kubectl -n techx-tf3 exec deploy/postgresql -- psql -U otelu -d otel -t -c "
  SELECT 'order' t, count(*), sum(hashtext(id::text)) FROM accounting.\"order\"
  UNION ALL SELECT 'orderitem', count(*), sum(hashtext(id::text)) FROM accounting.orderitem;"

# c) Kafka baseline
export MSYS_NO_PATHCONV=1
kubectl -n techx-tf3 exec deploy/kafka -c kafka -- \
  /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --all-groups
```

**Điều kiện đi tiếp:** cả 3 store Healthy, SLO ở mức baseline bình thường, load-generator đang chạy.

---

## 2. Hạ tầng (terraform, làm TRƯỚC mọi cutover — dựng không đụng gì đang chạy)

Dựng cả 3 managed service **song song với store cũ**. Bước này **zero-risk**: chưa ai trỏ vào chúng.

- **RDS**: PG **17.6** (khớp in-cluster), `db.t4g.micro`, **Multi-AZ**, private subnet, SG chỉ inbound
  5432 từ SG node group, `storage_encrypted=true`, backup retention ≥7 ngày.
  *(KHÔNG cần `rds.logical_replication` — kế hoạch dùng dump/restore, xem ADR 0008 §4.)*
- **ElastiCache**: engine **valkey 9.0**, `cache.t4g.micro`, 1 primary + 1 replica Multi-AZ,
  `transit_encryption_enabled=true`, `at_rest_encryption_enabled=true`, private subnet group.
- **MSK**: Kafka **3.9.x KRaft**, **3× `kafka.t3.small`** / 3 AZ, `encryption_in_transit.client_broker=TLS`,
  encryption at rest, private subnet.

```sh
# Nghiệm thu bước này: endpoint resolve được TỪ TRONG cluster, KHÔNG resolve từ ngoài
kubectl -n techx-tf3 run netcheck --rm -it --restart=Never --image=busybox:1.36 -- \
  sh -c "nc -zv <rds-endpoint> 5432; nc -zv <elasticache-endpoint> 6379"
```

## 3. Code + Secrets (deploy TRƯỚC cutover, cờ TLS TẮT → hành vi không đổi)

1. **Sửa 4 service** cho TLS gated bằng env (chi tiết ADR 0008 §2):
   - `cart/src/cartstore/ValkeyCartStore.cs:52` — `ssl=false` → đọc từ `VALKEY_TLS` (default `false`)
   - `checkout/kafka/producer.go` — `saramaConfig.Net.TLS.Enable` từ `KAFKA_TLS_ENABLED`
   - `accounting/Consumer.cs` — `SecurityProtocol` từ `KAFKA_TLS_ENABLED`
   - `fraud-detection/.../main.kt` — `SECURITY_PROTOCOL_CONFIG` từ `KAFKA_TLS_ENABLED`
1b. **`cart` cần thêm nhánh DUAL-WRITE** (`VALKEY_DUAL_WRITE_ADDR`, rỗng = tắt): mỗi `HashSet`+`KeyExpire`
   ghi thêm sang địa chỉ thứ 2. **Lỗi ở kho thứ 2 KHÔNG được làm fail request khách** (log + bỏ qua) —
   nếu không, dual-write biến ElastiCache thành SPOF mới ngay trong cửa sổ migrate. Điều kiện của
   chứng minh ADR 0008 §5.
2. **Build image** qua `build-push-ecr.yml` (build scoped theo service — xem comment `imageOverride`
   đầu `components:` trong `values-prod.yaml`; bump `imageOverride.tag` FULL string, **không** bump
   `default.image.tag`).
3. **Secrets Manager + External Secrets** → sinh 3 K8s secret đúng 3 format (.NET / Go-URL / libpq).
4. Deploy. **Verify hành vi KHÔNG đổi** (cờ TLS còn tắt, vẫn trỏ store cũ):

```sh
kubectl -n techx-tf3 get pods -l 'opentelemetry.io/name in (cart,checkout,accounting,fraud-detection)'
# → tất cả Running, 0 restart. SLO không đổi. Nếu lệch: dừng, revert, KHÔNG cutover.
```

---

## 4. Cutover Valkey → ElastiCache (**cửa sổ hội tụ 60 phút** — 0 mất giỏ)

**Cơ sở** ([ADR 0008](../adr/0008-mandate-08-managed-migration-cdo02.md) §5): `ValkeyCartStore.cs:174,199`
đặt **TTL 60 phút mỗi lần ghi**; đọc không gia hạn. ⇒ *giỏ còn sống tại T ⟺ được ghi trong [T−60ph, T]*
⇒ dual-write đủ **60 phút** thì ElastiCache **chắc chắn** chứa mọi giỏ còn sống. **Không cần bulk copy.**

> ⏱️ **Cửa sổ 60 phút là BẮT BUỘC, không phải khuyến nghị.** Rút ngắn = phá vỡ chứng minh = **mất giỏ thật**.
> Dùng **65-70 phút** cho biên an toàn.

```sh
# 0. XÁC NHẬN bất biến TTL còn đúng (code cart đổi thì chứng minh sụp)
kubectl -n techx-tf3 exec deploy/valkey-cart -- valkey-cli DBSIZE
kubectl -n techx-tf3 exec deploy/valkey-cart -- sh -c \
  'valkey-cli --scan 2>/dev/null | head -50 | while read k; do
     t=$(valkey-cli TTL "$k"); [ "$t" = "-1" ] && echo "VI PHAM: $k khong co TTL"; done; echo scan-done'
# → KHÔNG được có dòng "VI PHAM". Mọi key phải có TTL ≤ 3600s.

# 1. T0 — BẬT DUAL-WRITE (ghi cả 2, ĐỌC vẫn từ valkey cũ)
#    PR components.cart: VALKEY_DUAL_WRITE_ADDR=<elasticache>:6379, VALKEY_DUAL_WRITE_TLS=true
#    → hành vi khách KHÔNG đổi; valkey cũ vẫn là nguồn sự thật
date -u +"T0 = %H:%M UTC — dual-write BAT DAU"
kubectl -n techx-tf3 logs -l opentelemetry.io/name=cart --tail=20 | grep -iE "dual|elasticache|error"

# 2. CHỜ ĐỦ 60 PHÚT (dùng 65-70ph). Theo dõi key sinh ra bên mới:
watch -n60 'echo -n "elasticache DBSIZE="; redis-cli -h <elasticache> --tls DBSIZE'
# → số key bên mới TĂNG DẦN, tiệm cận số bên cũ

# 3. T0+60ph — KIỂM CHỨNG HỘI TỤ trước khi lật đọc (BẰNG CHỨNG NỘP)
#    Mọi key còn sống bên CŨ phải TỒN TẠI bên MỚI:
kubectl -n techx-tf3 exec deploy/valkey-cart -- sh -c 'valkey-cli --scan 2>/dev/null' > /tmp/old-keys.txt
miss=0; while read k; do
  redis-cli -h <elasticache> --tls EXISTS "$k" | grep -q '^1$' || { echo "THIEU: $k"; miss=$((miss+1)); }
done < /tmp/old-keys.txt
echo "So key thieu ben moi: $miss"    # → PHẢI = 0. Khác 0 → CHƯA lật đọc, chờ thêm/điều tra.

# 4. LẬT ĐỌC sang ElastiCache — ⚠️ VẪN GIỮ dual-write (đừng gỡ vội!)
#    PR components.cart: VALKEY_ADDR=<elasticache>:6379, VALKEY_TLS=true
#                        VALKEY_DUAL_WRITE_ADDR=<valkey-cu>:6379   ← ĐẢO CHIỀU: giờ ghi ngược về cũ
#    → valkey cũ tiếp tục đầy đủ ⇒ rollback lúc nào cũng KHÔNG mất gì
#    → chỉ gỡ dual-write SAU khi mentor nghiệm thu (bước 8)
#    → rolling restart (maxUnavailable:0 + preStop → 0 rớt request)

# 5. Verify
kubectl -n techx-tf3 logs -l opentelemetry.io/name=cart --tail=30 | grep -iE "error|connect|ssl"
# → thêm/xem giỏ trên storefront chạy được; Grafana: browse/cart ≥99.5%
```

**Rollback:** trả `VALKEY_ADDR` cũ + `VALKEY_TLS=false` → ~1 phút. **Không mất gì** — valkey cũ vẫn
được dual-write suốt cửa sổ nên vẫn đầy đủ.

---

## 5. Cutover Postgres → RDS ("đóng băng người ghi duy nhất", zero-downtime)

**Cơ sở** ([ADR 0008](../adr/0008-mandate-08-managed-migration-cdo02.md) §Hiện trạng #4): `accounting`
là **service DUY NHẤT ghi** vào Postgres, và nó ghi **async từ Kafka** với `EnableAutoCommit=false`.
`product-catalog`/`product-reviews` **chỉ đọc**. → Dừng `accounting` = Postgres read-only, mà **khách
không hề bị ảnh hưởng**.

> **Không dùng logical replication:** nó đòi `wal_level=logical`, in-cluster đang `wal_level=replica`
> → đổi phải **restart Postgres** → read outage cho browse → vỡ SLO. Cách dưới né hoàn toàn.

```sh
# 0. TIỀN ĐỀ: retention topic `orders` > cửa sổ cutover (mặc định 7 ngày ≫ ~10 phút)
export MSYS_NO_PATHCONV=1
kubectl -n techx-tf3 exec deploy/kafka -c kafka -- \
  /opt/kafka/bin/kafka-configs.sh --bootstrap-server localhost:9092 \
  --entity-type topics --entity-name orders --describe

# 1. ĐÓNG BĂNG người ghi duy nhất  → Postgres thành read-only
kubectl -n techx-tf3 scale deploy/accounting --replicas=0
#    ✅ checkout vẫn publish vào Kafka, đơn dồn ở topic `orders` (không mất)
#    ✅ product-catalog / product-reviews vẫn ĐỌC bình thường → KHÁCH KHÔNG BIẾT GÌ
#    Xác nhận không còn ghi:
kubectl -n techx-tf3 exec deploy/postgresql -- psql -U otelu -d otel -tAc \
  "SELECT count(*) FROM pg_stat_activity WHERE state='active' AND query ILIKE 'INSERT%';"   # → 0

# 2. DUMP + RESTORE (29 MB → vài giây). Dump full: schema + data + sequence
kubectl -n techx-tf3 exec deploy/postgresql -- pg_dump -U otelu -d otel --no-owner --no-acl \
  > /tmp/otel-full.sql
psql "host=<rds-endpoint> user=otelu dbname=otel sslmode=require" -f /tmp/otel-full.sql
#    (pg_dump full ĐÃ bao gồm setval() cho sequence → không lo primary key đụng,
#     khác với logical replication vốn không đồng bộ sequence)

# 3. PARITY CHECK — nguồn ĐANG ĐỨNG YÊN nên số khớp TUYỆT ĐỐI. CHỤP LẠI = bằng chứng nộp
for t in 'accounting."order"' accounting.orderitem accounting.shipping reviews.productreviews catalog.products; do
  o=$(kubectl -n techx-tf3 exec deploy/postgresql -- psql -U otelu -d otel -tAc "SELECT count(*) FROM $t;")
  n=$(psql "host=<rds-endpoint> user=otelu dbname=otel sslmode=require" -tAc "SELECT count(*) FROM $t;")
  echo "$t  old=$o  new=$n  $([ "$o" = "$n" ] && echo OK || echo MISMATCH)"
done
#    → mọi dòng phải OK. MISMATCH → dừng, KHÔNG cutover.

# 4. Đổi DB_CONNECTION_STRING của 3 service → RDS + sslmode=require  (PR → main → ArgoCD)
#      accounting:       Host=<rds>;Username=...;Password=...;Database=otel;SSL Mode=Require;Trust Server Certificate=true
#      product-catalog:  postgres://...@<rds>/otel?sslmode=require     ← ĐỔI TỪ sslmode=disable
#      product-reviews:  host=<rds> user=... password=... dbname=otel sslmode=require
#    (giá trị lấy từ secret — xem bước 3; KHÔNG hardcode)
#    product-catalog/product-reviews rolling restart: maxUnavailable:0 + preStop → 0 rớt request

# 5. THẢ người ghi trở lại, trỏ RDS  (accounting chạy 1 replica — ADR 0007 giữ 1 cho service phụ trợ)
kubectl -n techx-tf3 scale deploy/accounting --replicas=1
#    → offset CHƯA commit (EnableAutoCommit=false, REL-09) → replay sạch đơn dồn từ bước 1 vào RDS

# 6. Verify: đơn dồn đã vào RDS đủ, lag về 0
kubectl -n techx-tf3 exec deploy/kafka -c kafka -- \
  /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --group accounting          # → LAG = 0
psql "host=<rds-endpoint> ..." -tAc 'SELECT count(*) FROM accounting."order";'
#    → phải ≥ số ở bước 3 + số đơn PlaceOrder thành công trong cửa sổ (xem Grafana)
```

**Rollback:** trả `DB_CONNECTION_STRING` cũ → ~1 phút. Nếu `accounting` đã kịp ghi vào RDS: **reset
offset consumer group về mốc trước cutover** rồi replay vào postgres cũ — **không mất đơn nào** (Kafka
còn giữ message):
```sh
kubectl -n techx-tf3 scale deploy/accounting --replicas=0
kubectl -n techx-tf3 exec deploy/kafka -c kafka -- /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --group accounting --topic orders \
  --reset-offsets --to-datetime <mốc-trước-cutover> --execute
kubectl -n techx-tf3 scale deploy/accounting --replicas=1   # đã trỏ lại postgres cũ
```

---

## 6. Cutover Kafka → MSK (rủi ro cao nhất — `checkout` chặn đồng bộ trên publish)

Tận dụng `AutoOffsetReset=Earliest` → **không cần dual-consume**.

```sh
# 1. Tạo topic `orders` trên MSK — RF=3, min.insync.replicas=2
kafka-topics.sh --bootstrap-server <msk-tls-bootstrap>:9094 --command-config /tmp/client-tls.properties \
  --create --topic orders --partitions 3 --replication-factor 3 \
  --config min.insync.replicas=2
# /tmp/client-tls.properties:  security.protocol=SSL

# 2. Producer TRƯỚC: PR đổi components.checkout → KAFKA_ADDR=<msk>:9094, KAFKA_TLS_ENABLED=true
#    ⚠️ checkout dùng SyncProducer + acks=all → nếu MSK không nối được, PlaceOrder FAIL NGAY.
#    Theo dõi SÁT trong 5 phút đầu:
watch -n2 'kubectl -n techx-tf3 logs -l opentelemetry.io/name=checkout --tail=20 | grep -iE "kafka|error|tls"'
#    + Grafana: checkout success-rate PHẢI giữ ≥99%. Rớt → rollback NGAY (bước dưới).

# 3. ⚠️ BẮT BUỘC TRƯỚC KHI ĐO LAG: xác nhận KHÔNG CÒN pod checkout revision CŨ
#    Nếu còn 1 pod cũ đang produce vào Kafka cũ, message có thể rơi vào đó SAU lúc đo lag=0
#    → chuyển consumer đi → message MỒ CÔI VĨNH VIỄN. Đây là lỗi thứ tự tinh vi nhất của cả cutover.
kubectl -n techx-tf3 get rollout checkout-rollout -o jsonpath='{.status.phase}{"\n"}'   # → Healthy
kubectl -n techx-tf3 get pods -l opentelemetry.io/name=checkout \
  -o jsonpath='{range .items[*]}{.metadata.name}{" KAFKA_ADDR="}{.spec.containers[0].env[?(@.name=="KAFKA_ADDR")].value}{"\n"}{end}'
# → MỌI pod phải trỏ MSK. Còn bất kỳ pod nào trỏ kafka cũ → DỪNG, chờ rollout xong.

# 3b. Giờ mới chờ Kafka CŨ hút cạn — lag phải = 0 trước khi chuyển consumer
export MSYS_NO_PATHCONV=1
kubectl -n techx-tf3 exec deploy/kafka -c kafka -- \
  /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --all-groups
# → LAG = 0 cho cả `accounting` và `fraud-detection`

# 4. Consumer: PR đổi accounting + fraud-detection → KAFKA_ADDR=<msk>:9094, KAFKA_TLS_ENABLED=true
#    → group mới trên MSK, đọc từ Earliest → ăn sạch backlog tích từ bước 2

# 5. Verify: lag trên MSK về 0, không mất message
kafka-consumer-groups.sh --bootstrap-server <msk-tls-bootstrap>:9094 \
  --command-config /tmp/client-tls.properties --describe --all-groups
```

**Parity Kafka (bằng chứng nộp):** tổng message produce vào MSK từ lúc (2) == tổng consume của mỗi
group sau (4); `LAG = 0`; số đơn trong bảng `accounting."order"` tiếp tục tăng khớp với số PlaceOrder
thành công trên Grafana.

**Rollback:** trả `KAFKA_ADDR` cũ + `KAFKA_TLS_ENABLED=false` cho cả 3 service → ~1 phút.
⚠️ Message đã vào MSK mà chưa consume → phải **replay tay** sang kafka cũ. Đây là lý do bước (3) phải
đợi lag=0 và cửa sổ (2)→(4) nên **ngắn**.

---

## 7. Nghiệm thu với mentor

```sh
# 1. Không còn pod data tự host (yêu cầu #1 của directive)
kubectl -n techx-tf3 get pods | grep -E "postgresql|valkey|kafka"   # → rỗng (sau bước 8)

# 2. App trỏ managed
kubectl -n techx-tf3 get deploy checkout -o jsonpath='{..env}' | tr ',' '\n' | grep -iE "KAFKA_ADDR|TLS"

# 3. Endpoint riêng tư — KHÔNG resolve từ ngoài cluster
nslookup <rds-endpoint>          # từ máy ngoài → không ra / không nối được

# 4. Không còn credential plaintext
grep -rn "otelp\|otelu" "phase3 - information/techx-corp-chart/values.yaml"   # → rỗng
```

+ Trình: bảng parity trước/sau (bước 1 vs 5.5), Grafana SLO suốt cửa sổ cutover (checkout ≥99%),
[ADR 0008](../adr/0008-mandate-08-managed-migration-cdo02.md) ký tên.

## 8. Dọn dẹp — **ĐIỂM KHÔNG QUAY LUI**

**Chỉ làm sau khi mentor đã nghiệm thu xong cả 3 store.** Làm **đúng thứ tự** — mỗi bước đóng một đường lui:

```sh
# 1. Snapshot PVC cũ (EBS snapshot) — đường lui thảm hoạ cuối cùng, làm TRƯỚC TIÊN

# 2. PR gỡ dual-write của cart:  bỏ VALKEY_DUAL_WRITE_ADDR
#    ← từ giây phút này valkey cũ bắt đầu lạc hậu; rollback Valkey không còn zero-loss

# 3. PR gỡ khỏi values-prod.yaml + chart: components.postgresql / valkey-cart / kafka
# 4. PR gỡ gitops/infrastructure/datastore-pvc.yaml (postgresql-data, kafka-data) + valkey-cart PVC
# → merge → ArgoCD prune
```

> Bước 2 là **ranh giới thật**: trước nó, mọi thứ còn lùi được không mất dữ liệu. Đừng gộp bước 2 và 3
> vào cùng một PR — tách ra để còn kịp dừng.

---

## Lưu ý an toàn
- **Không đụng flagd** trong suốt cutover (Luật chơi — tắt/sửa = bị loại).
- Cutover **từng store một**, verify xong mới sang cái kế. Không gộp 3 PR vào 1 cửa sổ.
- Nếu SLO rớt bất kỳ lúc nào → **rollback ngay**, đừng cố "sửa tiếp cho xong".
- Mọi thay đổi qua **PR → main → ArgoCD**. Patch tay sẽ bị selfHeal revert giữa chừng cutover — nguy hiểm.
