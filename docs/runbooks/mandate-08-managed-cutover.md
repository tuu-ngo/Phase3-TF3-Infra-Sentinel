# Runbook — Mandate #8: cutover 3 store lên managed (RDS / ElastiCache / MSK)

Cơ sở kỹ thuật + đánh đổi: [ADR 0008](../adr/0008-mandate-08-managed-migration-cdo02.md).
Thứ tự: **Valkey → Postgres → Kafka** (dễ → khó). Mỗi store cutover **độc lập**, verify xong mới sang cái kế.

**Nguyên tắc xuyên suốt:**
- **KHÔNG xoá pod/PVC store cũ** cho tới khi mentor nghiệm thu cả 3. Store cũ = đường lui duy nhất.
- Giữ **tải nền thật** (load-generator ~20-50 user) suốt cutover — không có traffic thì "SLO không rớt" vô nghĩa.
- Mở **Grafana SLO dashboard** suốt quá trình (lấy hostname ở §0 — đừng hardcode).
- Mọi thay đổi đi qua **PR → main → ArgoCD sync** (cluster là GitOps, patch tay bị selfHeal revert).

---

## 0. Tham số — chạy khối này TRƯỚC, mọi lệnh phía dưới dùng lại các biến này

**Không hardcode giá trị nào.** Mọi endpoint/ID đều **tự lấy** — nên runbook vẫn đúng khi hạ tầng
dựng lại hoặc người khác chạy. Nếu một lệnh trả rỗng ⇒ tài nguyên đó chưa tồn tại, dừng và xử lý.

```sh
# --- Môi trường: KHÔNG có giá trị mặc định cho profile. Bạn PHẢI tự set. ---
# Đây là cutover production: copy-paste nhầm profile = thao tác lên SAI ACCOUNT.
: "${AWS_PROFILE:?PHAI set truoc, vd: export AWS_PROFILE=ten-profile-tro-dung-account-TF3}"
export AWS_REGION=ap-southeast-1
export CLUSTER=techx-corp-tf3
export NS=techx-tf3
export EXPECT_ACCOUNT=197826770971      # account TF3 tại thời điểm viết — đổi nếu TF chuyển account

# --- GUARD: sai account/cluster thì DỪNG NGAY, đừng để phát hiện sau khi đã đụng dữ liệu ---
ACCT=$(aws sts get-caller-identity --query Account --output text) || return 1 2>/dev/null || exit 1
if [ "$ACCT" != "$EXPECT_ACCOUNT" ]; then
  echo "DUNG LAI: profile '$AWS_PROFILE' dang tro account $ACCT, mong doi $EXPECT_ACCOUNT"
  return 1 2>/dev/null || exit 1
fi
aws eks describe-cluster --name "$CLUSTER" --region "$AWS_REGION" >/dev/null 2>&1 || {
  echo "DUNG LAI: khong thay cluster $CLUSTER trong account $ACCT/$AWS_REGION"
  return 1 2>/dev/null || exit 1; }
echo "OK: account=$ACCT region=$AWS_REGION cluster=$CLUSTER ns=$NS"

# --- Định danh tài nguyên do team đặt (khớp terraform) ---
export RDS_ID=techx-tf3-postgres
export ELASTICACHE_ID=techx-tf3-valkey
export MSK_NAME=techx-tf3-kafka

# --- Tự lấy: bastion + EKS endpoint ---
export BASTION_ID=$(aws ec2 describe-instances --region "$AWS_REGION" \
  --filters "Name=tag:Name,Values=${CLUSTER}-bastion" "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)
export EKS_HOST=$(aws eks describe-cluster --name "$CLUSTER" --region "$AWS_REGION" \
  --query 'cluster.endpoint' --output text | sed 's|https://||')
echo "BASTION_ID=$BASTION_ID  EKS_HOST=$EKS_HOST"     # rỗng ⇒ dừng

# --- Tự lấy: endpoint managed (SAU khi terraform apply — bước 2) ---
export RDS_HOST=$(aws rds describe-db-instances --region "$AWS_REGION" \
  --db-instance-identifier "$RDS_ID" --query 'DBInstances[0].Endpoint.Address' --output text)
export CACHE_HOST=$(aws elasticache describe-replication-groups --region "$AWS_REGION" \
  --replication-group-id "$ELASTICACHE_ID" \
  --query 'ReplicationGroups[0].NodeGroups[0].PrimaryEndpoint.Address' --output text)
export MSK_ARN=$(aws kafka list-clusters-v2 --region "$AWS_REGION" \
  --cluster-name-filter "$MSK_NAME" --query 'ClusterInfoList[0].ClusterArn' --output text)
export MSK_BOOTSTRAP=$(aws kafka get-bootstrap-brokers --region "$AWS_REGION" \
  --cluster-arn "$MSK_ARN" --query 'BootstrapBrokerStringSaslScram' --output text)
echo "RDS_HOST=$RDS_HOST"; echo "CACHE_HOST=$CACHE_HOST"; echo "MSK_BOOTSTRAP=$MSK_BOOTSTRAP"

# --- Tự lấy: credential từ Secrets Manager (KHÔNG gõ tay, KHÔNG paste vào chat/PR) ---
sec(){ aws secretsmanager get-secret-value --region "$AWS_REGION" --secret-id "$1" \
        --query SecretString --output text; }
export PG_USER=$(sec techx-tf3/postgres        | python -c 'import sys,json;print(json.load(sys.stdin)["username"])')
export PG_PASS=$(sec techx-tf3/postgres        | python -c 'import sys,json;print(json.load(sys.stdin)["password"])')
export CACHE_TOKEN=$(sec techx-tf3/elasticache-auth | python -c 'import sys,json;print(json.load(sys.stdin)["auth_token"])')
# ⚠️ KHÔNG kéo credential MSK về máy: pod CLI lấy thẳng từ K8s secret qua secretKeyRef (xem dưới).
#    Chỉ PG_PASS/CACHE_TOKEN buộc phải có ở đây vì psql/redis-cli chạy từ máy bạn qua tunnel.

# --- Store CŨ in-cluster (dùng cho dual-write ngược + rollback) ---
export VALKEY_OLD=valkey-cart:6379
export KAFKA_OLD=kafka:9092
```

**Mở tunnel + trỏ kubectl:**
```sh
aws ssm start-session --target "$BASTION_ID" --region "$AWS_REGION" \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters host="$EKS_HOST",portNumber="443",localPortNumber="8443"
# terminal khác:
aws eks update-kubeconfig --name "$CLUSTER" --region "$AWS_REGION"
ACCT=$(aws sts get-caller-identity --query Account --output text)
kubectl config set-cluster "arn:aws:eks:${AWS_REGION}:${ACCT}:cluster/${CLUSTER}" \
  --server=https://localhost:8443 --insecure-skip-tls-verify=true
```

**Grafana SLO dashboard:** lấy hostname hiện hành từ ingress thay vì hardcode —
```sh
kubectl -n "$NS" get ingress,httproute -A 2>/dev/null | grep -i grafana
# (hiện tại: https://grafana.arthur-ngo.org — đổi nếu Cloudflare hostname đổi)
```

### ⚠️ Kết nối tới store managed — ĐỌC TRƯỚC KHI CHẠY BẤT KỲ LỆNH NÀO

**RDS / ElastiCache / MSK nằm trong private subnet, SG chỉ mở từ SG node group + SG bastion.**
Máy bạn **KHÔNG nối thẳng được**. `psql -h $RDS_HOST` hay `redis-cli -h $CACHE_HOST` chạy từ laptop
sẽ **treo rồi timeout**. Có 2 đường, dùng đúng đường cho đúng store:

**(a) RDS + ElastiCache → tunnel SSM qua bastion** (đơn-endpoint, tunnel được):
```sh
# mỗi lệnh một terminal (hoặc thêm & để chạy nền)
aws ssm start-session --target "$BASTION_ID" --region "$AWS_REGION" \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters host="$RDS_HOST",portNumber="5432",localPortNumber="15432"
aws ssm start-session --target "$BASTION_ID" --region "$AWS_REGION" \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters host="$CACHE_HOST",portNumber="6379",localPortNumber="16379"
```
→ sau đó dùng `-h localhost -p 15432` (RDS) / `-p 16379` (ElastiCache).
**Điều kiện:** SG của RDS/ElastiCache phải cho inbound từ **SG bastion** (ngoài SG node group) — bước 2.
**Cần cài sẵn trên máy:** `psql` (client 17), `redis-cli`/`valkey-cli` có hỗ trợ `--tls`, `aws`, `kubectl`.

**(b) MSK → KHÔNG tunnel được, chạy CLI từ pod trong cluster.** Lý do: client Kafka bootstrap xong sẽ
bị broker trả về **advertised hostname riêng của từng broker** rồi kết nối thẳng tới đó — tunnel một
cổng không đủ.

Dựng **một pod CLI dùng chung** (ảnh Kafka đã có sẵn trong ECR), credential lấy qua **`secretKeyRef`**
— giá trị thật **không bao giờ nằm trong pod spec**, chỉ có *tham chiếu* tới secret. Đây là cách **mặc định**:

```sh
export KAFKA_IMAGE=$(kubectl -n "$NS" get deploy kafka \
  -o jsonpath='{.spec.template.spec.containers[0].image}')

kubectl -n "$NS" apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: mskcli
spec:
  restartPolicy: Never
  containers:
    - name: cli
      image: ${KAFKA_IMAGE}
      command: ["sleep", "7200"]        # sống 2h cho đủ cửa sổ cutover; xoá ở §8
      env:
        - name: MSK_USER                # ← chỉ THAM CHIẾU secret, không phải giá trị
          valueFrom:
            secretKeyRef: { name: kafka-scram, key: username }
        - name: MSK_PASS
          valueFrom:
            secretKeyRef: { name: kafka-scram, key: password }
EOF
kubectl -n "$NS" wait --for=condition=Ready pod/mskcli --timeout=120s

# Sinh file client config BÊN TRONG pod (credential đọc từ env do secretKeyRef bơm vào)
kubectl -n "$NS" exec mskcli -- sh -c 'umask 077; cat > /tmp/c.properties <<EOF
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="$MSK_USER" password="$MSK_PASS";
EOF'

# Helper — dùng: mskcli kafka-topics.sh --list
#                mskcli kafka-consumer-groups.sh --describe --all-groups
mskcli(){ tool="$1"; shift
  kubectl -n "$NS" exec mskcli -- \
    /opt/kafka/bin/"$tool" --bootstrap-server "$MSK_BOOTSTRAP" \
    --command-config /tmp/c.properties "$@"
}
```

**Vì sao cách này:** `secretKeyRef` chỉ ghi *tên secret + key* vào pod spec. `kubectl get pod -o yaml`
**không lộ credential**. Bootstrap string không phải bí mật nên truyền thẳng được. Điều kiện: K8s secret
`kafka-scram` (keys `username`/`password`) đã được External Secrets sinh từ
`AmazonMSK_techx-tf3/kafka-scram` — xem bước 3.

> 🔓 **Break-glass — CHỈ khi External Secrets chưa sync kịp và bạn đang phải xử lý sự cố.**
> `kubectl run mskcli-tmp --rm -i --restart=Never --image="$KAFKA_IMAGE" --env=MSK_USER=... --env=MSK_PASS=... ...`
> ⚠️ Cách này **ghi credential thẳng vào pod spec** → ai có `kubectl get pod -o yaml` trong `$NS` đọc được.
> **Không dùng cho thao tác thường.** Nếu đã lỡ dùng: **xoay lại SCRAM secret** sau khi xong.

## 1. Pre-flight (làm 1 lần, TRƯỚC mọi cutover)

```sh
# a) Baseline SLO — ghi lại để so sánh
#    Grafana SLO dashboard: checkout success-rate, browse/cart, storefront p95

# b) Baseline data parity — CHỤP LẠI, đây là bằng chứng nộp
kubectl -n "$NS" exec deploy/postgresql -- psql -U "$PG_USER" -d otel -t -c "
  SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY relname;"
kubectl -n "$NS" exec deploy/postgresql -- psql -U "$PG_USER" -d otel -t -c "
  SELECT 'order' t, count(*), sum(hashtext(id::text)) FROM accounting.\"order\"
  UNION ALL SELECT 'orderitem', count(*), sum(hashtext(id::text)) FROM accounting.orderitem;"

# c) Kafka baseline
export MSYS_NO_PATHCONV=1
kubectl -n "$NS" exec deploy/kafka -c kafka -- \
  /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --all-groups
```

**Điều kiện đi tiếp:** cả 3 store Healthy, SLO ở mức baseline bình thường, load-generator đang chạy.

---

## 2. Hạ tầng (terraform, làm TRƯỚC mọi cutover — dựng không đụng gì đang chạy)

Dựng cả 3 managed service **song song với store cũ**. Bước này **zero-risk**: chưa ai trỏ vào chúng.

- **RDS**: PG **17.6** (khớp in-cluster), `db.t4g.micro`, **Multi-AZ**, private subnet, `storage_encrypted=true`,
  backup retention ≥7 ngày. SG inbound 5432 từ **SG node group** (app) **+ SG bastion** (đường vận
  hành/migration — thiếu cái này thì tunnel ở §0 không nối được).
  *(KHÔNG cần `rds.logical_replication` — kế hoạch dùng dump/restore, xem ADR 0008 §4.)*
- **ElastiCache**: engine **valkey 9.0**, `cache.t4g.micro`, 1 primary + 1 replica Multi-AZ,
  `transit_encryption_enabled=true` (**bắt buộc** để dùng auth-token), `at_rest_encryption_enabled=true`,
  **`auth_token`** lấy từ secret `techx-tf3/elasticache-auth`, private subnet group.
  SG inbound 6379 từ **SG node group + SG bastion** (lý do như RDS).
- **MSK**: Kafka **3.9.x KRaft**, **3× `kafka.t3.small`** / 3 AZ, `encryption_in_transit.client_broker=TLS`,
  encryption at rest, private subnet, **`client_authentication.sasl.scram.enabled=true`**.
  SG inbound 9096 từ **SG node group** (MSK không tunnel được → thao tác qua pod, không cần SG bastion).
- **KMS + Secrets** (ADR 0008 §3): 1 **customer-managed KMS key**; 3 secret — `techx-tf3/postgres`,
  `techx-tf3/elasticache-auth`, và `AmazonMSK_techx-tf3/kafka-scram` (**tên PHẢI có tiền tố
  `AmazonMSK_`** và **PHẢI** mã hoá bằng CMK trên — MSK từ chối key `aws/secretsmanager` mặc định).

```sh
# Gắn secret SCRAM vào MSK (không có bước này thì SASL/SCRAM không auth được)
aws kafka batch-associate-scram-secret --region "$AWS_REGION" --cluster-arn "$MSK_ARN" \
  --secret-arn-list "$(aws secretsmanager describe-secret --region "$AWS_REGION" \
      --secret-id AmazonMSK_techx-tf3/kafka-scram --query ARN --output text)"
aws kafka list-scram-secrets --region "$AWS_REGION" --cluster-arn "$MSK_ARN"   # → phải thấy secret

# Nghiệm thu bước này: endpoint resolve được TỪ TRONG cluster, KHÔNG resolve từ ngoài
kubectl -n "$NS" run netcheck --rm -it --restart=Never --image=busybox:1.36 -- \
  sh -c "nc -zv $RDS_HOST 5432; nc -zv $CACHE_HOST 6379"
# MSK: kiểm tra bằng client có SASL (bootstrap SCRAM chạy cổng 9096, KHÔNG phải 9094)
echo "$MSK_BOOTSTRAP"    # → phải là chuỗi *:9096
```

## 3. Code + Secrets (deploy TRƯỚC cutover, cờ TLS TẮT → hành vi không đổi)

1. **Sửa 4 service** cho **TLS + auth** gated bằng env, mặc định tắt (chi tiết ADR 0008 §2):
   - `cart/src/cartstore/ValkeyCartStore.cs:52` — `ssl=false` hardcode → `ssl=$VALKEY_TLS` +
     `password=$VALKEY_AUTH_TOKEN` (default: `false` / rỗng = y như hiện tại)
   - `checkout/kafka/producer.go` — `KAFKA_SECURITY_PROTOCOL` (default `PLAINTEXT`) → khi `SASL_SSL`:
     `Net.TLS.Enable=true` + `Net.SASL` SCRAM-SHA-512.
     ⚠️ **sarama không có sẵn SCRAM client — phải tự implement `sarama.SCRAMClient`** (thường dùng
     `github.com/xdg-go/scram`). Đây là phần code nặng nhất của cả mandate, đừng ước lượng là "một cờ".
   - `accounting/Consumer.cs` — `SecurityProtocol=SaslSsl`, `SaslMechanism=ScramSha512`,
     `SaslUsername`/`SaslPassword` từ env (confluent-kafka-dotnet hỗ trợ sẵn)
   - `fraud-detection/.../main.kt` — `security.protocol=SASL_SSL`, `sasl.mechanism=SCRAM-SHA-512`,
     `sasl.jaas.config` (client Kafka Java hỗ trợ sẵn)
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
kubectl -n "$NS" get pods -l 'opentelemetry.io/name in (cart,checkout,accounting,fraud-detection)'
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
kubectl -n "$NS" exec deploy/valkey-cart -- valkey-cli DBSIZE
kubectl -n "$NS" exec deploy/valkey-cart -- sh -c \
  'valkey-cli --scan 2>/dev/null | head -50 | while read k; do
     t=$(valkey-cli TTL "$k"); [ "$t" = "-1" ] && echo "VI PHAM: $k khong co TTL"; done; echo scan-done'
# → KHÔNG được có dòng "VI PHAM". Mọi key phải có TTL ≤ 3600s.

# 1. T0 — BẬT DUAL-WRITE (ghi cả 2, ĐỌC vẫn từ valkey cũ)
#    PR components.cart: VALKEY_DUAL_WRITE_ADDR=$CACHE_HOST:6379, VALKEY_DUAL_WRITE_TLS=true (token tu secret)
#    → hành vi khách KHÔNG đổi; valkey cũ vẫn là nguồn sự thật
date -u +"T0 = %H:%M UTC — dual-write BAT DAU"
kubectl -n "$NS" logs -l opentelemetry.io/name=cart --tail=20 | grep -iE "dual|elasticache|error"

# 2. CHỜ ĐỦ 60 PHÚT (dùng 65-70ph). Theo dõi key sinh ra bên mới:
#    (cần tunnel ElastiCache ở §0 — localhost:16379)
watch -n60 'echo -n "elasticache DBSIZE="; redis-cli -h localhost -p 16379 --tls -a "$CACHE_TOKEN" --no-auth-warning DBSIZE'
# → số key bên mới TĂNG DẦN, tiệm cận số bên cũ

# 3. T0+60ph — KIỂM CHỨNG HỘI TỤ trước khi lật đọc (BẰNG CHỨNG NỘP)
#    Mọi key còn sống bên CŨ phải TỒN TẠI bên MỚI:
kubectl -n "$NS" exec deploy/valkey-cart -- sh -c 'valkey-cli --scan 2>/dev/null' > /tmp/old-keys.txt
wc -l < /tmp/old-keys.txt      # số key bên cũ — ghi lại
miss=0
while read -r k; do
  redis-cli -h localhost -p 16379 --tls -a "$CACHE_TOKEN" --no-auth-warning EXISTS "$k" \
    | grep -q '^1$' || { echo "THIEU: $k"; miss=$((miss+1)); }
done < /tmp/old-keys.txt
echo "So key thieu ben moi: $miss"    # → PHẢI = 0. Khác 0 → CHƯA lật đọc, chờ thêm/điều tra.
#    Lưu ý: key hết hạn TRONG lúc quét sẽ báo THIEU oan (race lành tính) — quét lại để xác nhận,
#    đừng vội kết luận hỏng.

# 4. LẬT ĐỌC sang ElastiCache — ⚠️ VẪN GIỮ dual-write (đừng gỡ vội!)
#    PR components.cart: VALKEY_ADDR=$CACHE_HOST:6379, VALKEY_TLS=true, VALKEY_AUTH_TOKEN (từ secret)
#                        VALKEY_DUAL_WRITE_ADDR=$VALKEY_OLD   ← ĐẢO CHIỀU: giờ ghi ngược về cũ
#    → valkey cũ tiếp tục đầy đủ ⇒ rollback lúc nào cũng KHÔNG mất gì
#    → chỉ gỡ dual-write SAU khi mentor nghiệm thu (bước 8)
#    → rolling restart (maxUnavailable:0 + preStop → 0 rớt request)

# 5. Verify
kubectl -n "$NS" logs -l opentelemetry.io/name=cart --tail=30 | grep -iE "error|connect|ssl"
# → thêm/xem giỏ trên storefront chạy được; Grafana: browse/cart ≥99.5%
```

**Rollback:** trả `VALKEY_ADDR`=`$VALKEY_OLD` + `VALKEY_TLS=false` + bỏ `VALKEY_AUTH_TOKEN` → ~1 phút. **Không mất gì** — valkey cũ vẫn
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
# 0. TIỀN ĐỀ: retention topic `orders` > cửa sổ cutover
export MSYS_NO_PATHCONV=1
#    Topic `orders` KHÔNG có override riêng → nó thừa kế default của broker.
#    (Lệnh --entity-type topics chỉ in "Dynamic configs..." RỖNG, KHÔNG chứng minh được gì —
#     phải hỏi broker default:)
kubectl -n "$NS" exec deploy/kafka -c kafka -- sh -c \
  "/opt/kafka/bin/kafka-configs.sh --bootstrap-server localhost:9092 \
   --entity-type brokers --entity-name 1 --describe --all 2>/dev/null | grep -E 'log.retention.(hours|bytes)='"
# → mong đợi: log.retention.hours=168 (7 ngày), log.retention.bytes=-1 ≫ cửa sổ ~10 phút

# 1. ĐÓNG BĂNG người ghi duy nhất  → Postgres thành read-only
export T_FREEZE=$(date -u +%Y-%m-%dT%H:%M:%S.000)   # ⚠️ GHI LẠI — rollback cần mốc này để reset offset
echo "T_FREEZE=$T_FREEZE"                            #    (định dạng .sss là BẮT BUỘC với --to-datetime)
kubectl -n "$NS" scale deploy/accounting --replicas=0
kubectl -n "$NS" wait --for=delete pod -l opentelemetry.io/name=accounting --timeout=90s
#    ✅ checkout vẫn publish vào Kafka, đơn dồn ở topic `orders` (không mất)
#    ✅ product-catalog / product-reviews vẫn ĐỌC bình thường → KHÁCH KHÔNG BIẾT GÌ
#    BẰNG CHỨNG "đã đóng băng" = KHÔNG CÒN POD accounting (đây mới là check chính):
kubectl -n "$NS" get pods -l opentelemetry.io/name=accounting    # → "No resources found"
#    Kiểm tra phụ (không đủ để kết luận — EF Core dùng INSERT tham số hoá, có thể không khớp LIKE):
kubectl -n "$NS" exec deploy/postgresql -- psql -U "$PG_USER" -d otel -tAc \
  "SELECT count(*) FROM pg_stat_activity WHERE state='active' AND datname='otel' AND pid<>pg_backend_pid();"

# 2. DUMP + RESTORE (29 MB → vài giây). Dump full: schema + data + sequence
#    (cần tunnel RDS ở §0 — localhost:15432)
kubectl -n "$NS" exec deploy/postgresql -- pg_dump -U "$PG_USER" -d otel --no-owner --no-acl \
  > /tmp/otel-full.sql
PGPASSWORD="$PG_PASS" psql "host=localhost port=15432 user=$PG_USER dbname=otel sslmode=require" \
  -v ON_ERROR_STOP=1 -f /tmp/otel-full.sql
#    ON_ERROR_STOP=1: restore lỗi giữa chừng phải DỪNG, không được im lặng đi tiếp rồi parity sai.
#    (pg_dump full ĐÃ bao gồm setval() cho sequence → không lo primary key đụng,
#     khác với logical replication vốn không đồng bộ sequence)

# 3. PARITY CHECK — nguồn ĐANG ĐỨNG YÊN nên số khớp TUYỆT ĐỐI. CHỤP LẠI = bằng chứng nộp
for t in 'accounting."order"' accounting.orderitem accounting.shipping reviews.productreviews catalog.products; do
  o=$(kubectl -n "$NS" exec deploy/postgresql -- psql -U "$PG_USER" -d otel -tAc "SELECT count(*) FROM $t;" | tr -d '[:space:]')
  n=$(PGPASSWORD="$PG_PASS" psql "host=localhost port=15432 user=$PG_USER dbname=otel sslmode=require" \
        -tAc "SELECT count(*) FROM $t;" | tr -d '[:space:]')
  echo "$t  old=$o  new=$n  $([ "$o" = "$n" ] && echo OK || echo MISMATCH)"
done
#    → mọi dòng phải OK. MISMATCH → dừng, KHÔNG cutover.

# 4. Đổi DB_CONNECTION_STRING của 3 service → RDS + sslmode=require  (PR → main → ArgoCD)
#      accounting:       Host=$RDS_HOST;Username=...;Password=...;Database=otel;SSL Mode=Require;Trust Server Certificate=true
#      product-catalog:  postgres://...@$RDS_HOST/otel?sslmode=require     ← ĐỔI TỪ sslmode=disable
#      product-reviews:  host=$RDS_HOST user=... password=... dbname=otel sslmode=require
#    (giá trị lấy từ secret — xem bước 3; KHÔNG hardcode)
#    product-catalog/product-reviews rolling restart: maxUnavailable:0 + preStop → 0 rớt request

# 5. THẢ người ghi trở lại, trỏ RDS  (accounting chạy 1 replica — ADR 0007 giữ 1 cho service phụ trợ)
kubectl -n "$NS" scale deploy/accounting --replicas=1
#    → offset CHƯA commit (EnableAutoCommit=false, REL-09) → replay sạch đơn dồn từ bước 1 vào RDS

# 6. Verify: đơn dồn đã vào RDS đủ, lag về 0
kubectl -n "$NS" exec deploy/kafka -c kafka -- \
  /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --group accounting          # → LAG = 0
PGPASSWORD="$PG_PASS" psql "host=localhost port=15432 user=$PG_USER dbname=otel sslmode=require" \
  -tAc 'SELECT count(*) FROM accounting."order";'
#    → phải ≥ số ở bước 3 + số đơn PlaceOrder thành công trong cửa sổ (xem Grafana)
```

**Rollback:** trả `DB_CONNECTION_STRING` cũ → ~1 phút. Nếu `accounting` đã kịp ghi vào RDS: **reset
offset consumer group về mốc trước cutover** rồi replay vào postgres cũ — **không mất đơn nào** (Kafka
còn giữ message):
```sh
# GHI LẠI MỐC NÀY NGAY TRƯỚC BƯỚC 1 (đóng băng) — không có nó thì không reset offset đúng chỗ:
#   export T_FREEZE=$(date -u +%Y-%m-%dT%H:%M:%S.000)
kubectl -n "$NS" scale deploy/accounting --replicas=0
kubectl -n "$NS" wait --for=delete pod -l opentelemetry.io/name=accounting --timeout=90s
kubectl -n "$NS" exec deploy/kafka -c kafka -- /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --group accounting --topic orders \
  --reset-offsets --to-datetime "$T_FREEZE" --execute
#    (định dạng BẮT BUỘC: YYYY-MM-DDTHH:MM:SS.sss — thiếu phần .sss là lệnh báo lỗi)
#    reset-offsets chỉ chạy khi consumer group KHÔNG có member nào → phải scale 0 trước
kubectl -n "$NS" scale deploy/accounting --replicas=1   # đã trỏ lại postgres cũ
```

---

## 6. Cutover Kafka → MSK (rủi ro cao nhất — `checkout` chặn đồng bộ trên publish)

Tận dụng `AutoOffsetReset=Earliest` → **không cần dual-consume**.

```sh
# 1. Tạo topic `orders` trên MSK — RF=3, min.insync.replicas=2
#    (dùng helper mskcli ở §0 — MSK KHÔNG tunnel được, phải chạy từ pod trong cluster)
mskcli kafka-topics.sh --create --topic orders --partitions 3 --replication-factor 3 \
  --config min.insync.replicas=2
mskcli kafka-topics.sh --describe --topic orders     # xác nhận RF=3, min.insync=2


# 2. Producer TRƯỚC: PR đổi components.checkout → KAFKA_ADDR=$MSK_BOOTSTRAP, KAFKA_SECURITY_PROTOCOL=SASL_SSL, KAFKA_SASL_USERNAME/_PASSWORD (tu secret)
#    ⚠️ checkout dùng SyncProducer + acks=all → nếu MSK không nối được, PlaceOrder FAIL NGAY.
#    Theo dõi SÁT trong 5 phút đầu:
watch -n2 'kubectl -n "$NS" logs -l opentelemetry.io/name=checkout --tail=20 | grep -iE "kafka|error|tls"'
#    + Grafana: checkout success-rate PHẢI giữ ≥99%. Rớt → rollback NGAY (bước dưới).

# 3. ⚠️ BẮT BUỘC TRƯỚC KHI ĐO LAG: xác nhận KHÔNG CÒN pod checkout revision CŨ
#    Nếu còn 1 pod cũ đang produce vào Kafka cũ, message có thể rơi vào đó SAU lúc đo lag=0
#    → chuyển consumer đi → message MỒ CÔI VĨNH VIỄN. Đây là lỗi thứ tự tinh vi nhất của cả cutover.
kubectl -n "$NS" get rollout checkout-rollout -o jsonpath='{.status.phase}{"\n"}'   # → Healthy
kubectl -n "$NS" get pods -l opentelemetry.io/name=checkout \
  -o jsonpath='{range .items[*]}{.metadata.name}{" KAFKA_ADDR="}{.spec.containers[0].env[?(@.name=="KAFKA_ADDR")].value}{"\n"}{end}'
# → MỌI pod phải trỏ MSK. Còn bất kỳ pod nào trỏ kafka cũ → DỪNG, chờ rollout xong.

# 3b. Giờ mới chờ Kafka CŨ hút cạn — lag phải = 0 trước khi chuyển consumer
export MSYS_NO_PATHCONV=1
kubectl -n "$NS" exec deploy/kafka -c kafka -- \
  /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --all-groups
# → LAG = 0 cho cả `accounting` và `fraud-detection`

# 4. Consumer: PR đổi accounting + fraud-detection → KAFKA_ADDR=$MSK_BOOTSTRAP, KAFKA_SECURITY_PROTOCOL=SASL_SSL, KAFKA_SASL_USERNAME/_PASSWORD (tu secret)
#    → group mới trên MSK, đọc từ Earliest → ăn sạch backlog tích từ bước 2

# 5. Verify: lag trên MSK về 0, không mất message
mskcli kafka-consumer-groups.sh --describe --all-groups
```

**Parity Kafka (bằng chứng nộp):** tổng message produce vào MSK từ lúc (2) == tổng consume của mỗi
group sau (4); `LAG = 0`; số đơn trong bảng `accounting."order"` tiếp tục tăng khớp với số PlaceOrder
thành công trên Grafana.

**Rollback:** trả `KAFKA_ADDR`=`$KAFKA_OLD` + `KAFKA_SECURITY_PROTOCOL=PLAINTEXT` cho cả 3 service → ~1 phút.
⚠️ Message đã vào MSK mà chưa consume → phải **replay tay** sang kafka cũ. Đây là lý do bước (3) phải
đợi lag=0 và cửa sổ (2)→(4) nên **ngắn**.

---

## 7. Nghiệm thu với mentor

```sh
# 1. Không còn pod data tự host (yêu cầu #1 của directive)
kubectl -n "$NS" get pods | grep -E "postgresql|valkey-cart|kafka"   # → rỗng (sau §8)

# 2. App trỏ managed + có auth
kubectl -n "$NS" get deploy checkout -o jsonpath='{range .spec.template.spec.containers[0].env[*]}{.name}={.value}{"\n"}{end}' \
  | grep -iE "KAFKA_ADDR|KAFKA_SECURITY_PROTOCOL"     # → *:9096 + SASL_SSL
kubectl -n "$NS" get deploy cart -o jsonpath='{range .spec.template.spec.containers[0].env[*]}{.name}={.value}{"\n"}{end}' \
  | grep -iE "VALKEY_ADDR|VALKEY_TLS"

# 3. Endpoint riêng tư — chứng minh bằng KHÔNG KẾT NỐI ĐƯỢC, không phải bằng DNS.
#    (DNS của RDS/ElastiCache VẪN resolve ra IP private từ ngoài — đừng dùng nslookup làm bằng chứng.)
#    Từ máy ngoài VPC (TẮT tunnel §0 trước khi thử):
timeout 10 bash -c "</dev/tcp/$RDS_HOST/5432" 2>&1 || echo "OK: khong noi duoc tu ngoai VPC"
#    Từ trong cluster → PHẢI nối được:
kubectl -n "$NS" run netcheck --rm -i --restart=Never --image=busybox:1.36 -- \
  sh -c "nc -zv $RDS_HOST 5432 && nc -zv $CACHE_HOST 6379"
#    Và xác nhận không có public endpoint:
aws rds describe-db-instances --region "$AWS_REGION" --db-instance-identifier "$RDS_ID" \
  --query 'DBInstances[0].PubliclyAccessible'        # → false

# 4. Không còn credential plaintext trong git
grep -rn "otelp\|otelu" "phase3 - information/techx-corp-chart/values.yaml" \
  "phase3 - information/deploy/values-prod.yaml"     # → rỗng
```

+ Trình: **bảng parity** trước/sau (§1 mục b — baseline, so với §5 bước 3), **key convergence Valkey**
(§4 bước 3, `miss=0`), **lag Kafka = 0** (§6 bước 5), Grafana SLO suốt cả 3 cửa sổ cutover
(checkout ≥99%), và [ADR 0008](../adr/0008-mandate-08-managed-migration-cdo02.md) ký tên.

## 8. Dọn dẹp — **ĐIỂM KHÔNG QUAY LUI**

**Chỉ làm sau khi mentor đã nghiệm thu xong cả 3 store.** Làm **đúng thứ tự** — mỗi bước đóng một đường lui:

```sh
# 0. Dọn pod CLI tạm + tunnel (làm ngay khi hết cần, đừng để pod cầm secret sống lang thang)
kubectl -n "$NS" delete pod mskcli --ignore-not-found
#    + đóng các phiên SSM tunnel RDS/ElastiCache ở §0

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
