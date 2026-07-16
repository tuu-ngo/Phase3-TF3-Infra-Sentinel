# Mandate 08 - Baseline dữ liệu managed migration

**Thời điểm chụp:** 2026-07-16 20:20 +07  
**Phạm vi:** read-only baseline cho kế hoạch đưa PostgreSQL, Valkey, Kafka từ pod in-cluster sang RDS, ElastiCache, MSK.  
**Nguồn quyết định:** [ADR 0009](../adr/0009-mandate-08-managed-migration-cdo02.md) và [runbook cutover](../runbooks/mandate-08-managed-cutover.md).  
**Account live:** `197826770971` (`arn:aws:iam::197826770971:user/cdo-2-admin-team`)  
**Cluster:** `techx-corp-tf3`, region `ap-southeast-1`, namespace `techx-tf3`

## Kết luận nhanh

Mandate 08 hiện **chưa được triển khai trên hạ tầng live**. AWS account chưa có RDS, ElastiCache hoặc MSK đang chạy cho TF3; toàn bộ dữ liệu production hiện vẫn nằm trong ba pod self-hosted trong EKS:

| Store | Trạng thái hiện tại | Managed target | Kết luận |
|---|---|---|---|
| PostgreSQL | Pod `postgresql`, PVC `postgresql-data` 2Gi | RDS PostgreSQL 17.6 | Chưa migrate |
| Valkey | Pod `valkey-cart`, PVC `valkey-cart` 1Gi | ElastiCache Valkey 9.0 | Chưa migrate |
| Kafka | Pod `kafka`, PVC `kafka-data` 3Gi | MSK Kafka 3.9.x KRaft | Chưa migrate |

Điểm tốt: dữ liệu hiện khá nhỏ, version managed khớp version self-hosted, Kafka retention 7 ngày, Valkey key mẫu đều có TTL. Điểm rủi ro lớn nhất vẫn là thứ tự cutover Kafka và code hỗ trợ TLS/auth/dual-write chưa được xác nhận là đã deploy.

## GitOps và cluster

ArgoCD đang trỏ `main`, không còn trỏ nhánh deploy cũ:

| App | Health | Sync | Revision | Target | Path |
|---|---|---|---|---|---|
| `techx-corp` | Healthy | Synced | `ca41a2c19e78ce516085ece53758a17a86efcafa` | `main` | `phase3 - information/techx-corp-chart` |
| `techx-infrastructure-app` | Healthy | Synced | `ca41a2c19e78ce516085ece53758a17a86efcafa` | `main` | `gitops/infrastructure` |
| `techx-edge` | Healthy | Synced | `ca41a2c19e78ce516085ece53758a17a86efcafa` | `main` | `gitops/edge` |

EKS:

| Thuộc tính | Giá trị |
|---|---|
| Cluster | `techx-corp-tf3` |
| Status | `ACTIVE` |
| Version | `1.35` |
| Endpoint private | `true` |
| Endpoint public | `false` |

## AWS managed services

Kết quả read-only ở account `197826770971`, region `ap-southeast-1`:

| Dịch vụ | Kết quả |
|---|---|
| RDS DB clusters | Không có |
| RDS DB instances | Không có |
| ElastiCache cache clusters | Không có |
| ElastiCache replication groups | Không có |
| MSK clusters | Không có |

Diễn giải: Mandate 08 mới có ADR/runbook; hạ tầng managed chưa được dựng live. PR tiếp theo không nên xóa pod/PVC cũ, mà phải dựng managed service song song trước.

## Kubernetes data stores hiện tại

Pods:

| Pod | Ready | Status | Restarts | Age | Node |
|---|---:|---|---:|---|---|
| `kafka-55948d947f-7fxj8` | 1/1 | Running | 0 | 33h | `ip-10-0-26-153.ap-southeast-1.compute.internal` |
| `postgresql-6d8bf96cff-xp8hs` | 1/1 | Running | 0 | 20h | `ip-10-0-4-166.ap-southeast-1.compute.internal` |
| `valkey-cart-c98648b76-g8lm7` | 1/1 | Running | 0 | 20h | `ip-10-0-4-166.ap-southeast-1.compute.internal` |

Services:

| Service | Type | ClusterIP | Ports |
|---|---|---|---|
| `postgresql` | ClusterIP | `172.20.84.197` | `5432/TCP` |
| `valkey-cart` | ClusterIP | `172.20.42.48` | `6379/TCP` |
| `kafka` | ClusterIP | `172.20.162.93` | `9092/TCP`, `9093/TCP` |

PVC:

| PVC | Status | Volume | Capacity | StorageClass |
|---|---|---|---:|---|
| `postgresql-data` | Bound | `pvc-65777d66-5c41-4186-80b7-a0931167a634` | 2Gi | `gp2` |
| `valkey-cart` | Bound | `pvc-564c4984-9b3e-488d-8b0a-7db0806a2edd` | 1Gi | `gp2` |
| `kafka-data` | Bound | `pvc-3d2172ad-7068-4302-85e1-990195aafc9e` | 3Gi | `gp2` |

Images:

| Deployment | Ready | Desired | Image |
|---|---:|---:|---|
| `postgresql` | 1 | 1 | `postgres:17.6` |
| `valkey-cart` | 1 | 1 | repo `valkey/valkey`, tag `9.0.1-alpine3.23` |
| `kafka` | 1 | 1 | `197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp:58b13f2-kafka` |

## PostgreSQL baseline

| Check | Giá trị |
|---|---|
| Version | PostgreSQL 17.6 |
| Database | `otel` |
| Size | `38194323` bytes, khoảng 36.4 MiB |
| Extension | `plpgsql` |

User tables:

| Schema | Table | Approx live tuples |
|---|---|---:|
| `accounting` | `order` | 39348 |
| `accounting` | `orderitem` | 72058 |
| `accounting` | `shipping` | 39348 |
| `catalog` | `products` | 10 |
| `reviews` | `productreviews` | 50 |

Ý nghĩa cho Mandate 08:

- Dump/restore sang RDS có kích thước nhỏ, khả thi trong cửa sổ ngắn.
- Vẫn phải re-audit ngay trước cutover rằng `accounting` là writer duy nhất vào PostgreSQL.
- Không được dùng số `n_live_tup` làm parity cuối cùng; khi cutover thật phải dùng `count(*)` và checksum theo runbook.

## Valkey baseline

| Check | Giá trị |
|---|---|
| Server | Valkey 9.0.1 |
| Mode | standalone |
| Port | 6379 |
| DBSIZE | 4085 keys |
| TTL sample | 50/50 key mẫu có TTL dương |

TTL 50 key đầu dao động trong mẫu từ `40` đến `3586` giây, không thấy key `-1` trong mẫu. Điều này ủng hộ lập luận trong ADR 0009: nếu dual-write chạy đủ 60 phút hoặc an toàn hơn 65-70 phút, mọi cart còn sống sẽ được ghi sang ElastiCache trước khi lật read.

Điều kiện cần trước khi cutover Valkey:

- Code `cart` phải có `VALKEY_TLS`, `VALKEY_AUTH_TOKEN`, và `VALKEY_DUAL_WRITE_ADDR`.
- Lỗi ghi sang target dual-write không được làm fail request khách.
- Phải chạy lại scan TTL trước T0; nếu còn key không TTL thì lập luận 60 phút không còn đủ.

## Kafka baseline

Topics:

| Topic | Partition | Replication factor | Ghi chú |
|---|---:|---:|---|
| `orders` | 1 | 1 | Topic chính trên luồng checkout/accounting/fraud |
| `__consumer_offsets` | system | system | Consumer offsets |

Consumer groups tại thời điểm chụp:

| Group | Topic | Current offset | Log end offset | Lag |
|---|---|---:|---:|---:|
| `accounting` | `orders` | 33950 | 33951 | 1 |
| `fraud-detection` | `orders` | 33949 | 33951 | 2 |

Broker retention:

| Config | Giá trị |
|---|---|
| `log.retention.hours` | 168 |
| `log.retention.bytes` | -1 |

Ý nghĩa cho Mandate 08:

- Retention 7 ngày lớn hơn rất nhiều so với cửa sổ cutover dự kiến, đủ làm vùng đệm cho Postgres freeze và Kafka producer/consumer switch.
- Kafka self-hosted hiện chỉ 1 broker, RF=1; MSK target theo ADR phải là 3 broker, RF=3, `min.insync.replicas=2`.
- Cutover Kafka phải tuân thủ thứ tự: producer `checkout` sang MSK xong toàn bộ pod, xác nhận không còn producer cũ, đợi Kafka cũ lag = 0, rồi mới chuyển consumer.

## Việc cần làm tiếp theo

1. Tạo PR hạ tầng dựng song song RDS, ElastiCache, MSK, Secrets Manager, KMS, security group private-only. Chỉ chạy `terraform plan` cho review; chưa apply nếu chưa có cửa sổ và xác nhận.
2. Tạo PR code cho TLS/auth gated bằng env:
   - `cart`: Valkey TLS/auth + dual-write.
   - `checkout`: Kafka SASL_SSL/SCRAM cho Sarama.
   - `accounting`: Kafka SASL_SSL/SCRAM.
   - `fraud-detection`: Kafka SASL_SSL/SCRAM.
3. Tạo PR External Secrets và values để bỏ credential plaintext khỏi chart, nhưng default vẫn trỏ store cũ cho tới khi cutover.
4. Trước cutover, chạy lại baseline này và lưu evidence mới:
   - AWS managed resources đã tồn tại và private-only.
   - PostgreSQL exact `count(*)` + checksum.
   - Valkey DBSIZE + TTL scan không có key `-1`.
   - Kafka topic, offset, lag, retention.
   - Grafana checkout SLO baseline.
5. Cutover từng store theo thứ tự runbook: Valkey, PostgreSQL, Kafka. Không gộp ba store vào cùng một PR/cửa sổ.
6. Chỉ xóa pod/PVC self-hosted sau khi mentor nghiệm thu đủ evidence cả ba store. Đây là điểm không quay lui.

## Lệnh đã chạy

Các lệnh dưới đây đều read-only:

```powershell
aws sts get-caller-identity
aws eks describe-cluster --name techx-corp-tf3 --region ap-southeast-1
aws rds describe-db-clusters --region ap-southeast-1
aws rds describe-db-instances --region ap-southeast-1
aws elasticache describe-cache-clusters --region ap-southeast-1 --show-cache-node-info
aws elasticache describe-replication-groups --region ap-southeast-1
aws kafka list-clusters-v2 --region ap-southeast-1

kubectl get applications.argoproj.io -n argocd techx-corp techx-infrastructure-app techx-edge
kubectl get pods -n techx-tf3 -l 'opentelemetry.io/name in (postgresql,valkey-cart,kafka)' -o wide
kubectl get svc -n techx-tf3 postgresql valkey-cart kafka -o wide
kubectl get pvc -n techx-tf3 postgresql-data valkey-cart kafka-data
kubectl get deploy -n techx-tf3 postgresql valkey-cart kafka
kubectl -n techx-tf3 exec deploy/postgresql -- psql -U otelu -d otel -tAc "SELECT version();"
kubectl -n techx-tf3 exec deploy/postgresql -- psql -U otelu -d otel -tAc "SELECT pg_database_size('otel');"
kubectl -n techx-tf3 exec deploy/postgresql -- psql -U otelu -d otel -tAc "SELECT schemaname, relname, n_live_tup FROM pg_stat_user_tables ORDER BY schemaname, relname;"
kubectl -n techx-tf3 exec deploy/valkey-cart -- valkey-cli INFO server
kubectl -n techx-tf3 exec deploy/valkey-cart -- valkey-cli DBSIZE
kubectl -n techx-tf3 exec deploy/valkey-cart -- sh -c 'valkey-cli --scan 2>/dev/null | head -50 | xargs -r -I{} valkey-cli TTL "{}"'
kubectl -n techx-tf3 exec deploy/kafka -c kafka -- /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
kubectl -n techx-tf3 exec deploy/kafka -c kafka -- /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic orders
kubectl -n techx-tf3 exec deploy/kafka -c kafka -- /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --all-groups
kubectl -n techx-tf3 exec deploy/kafka -c kafka -- sh -c "/opt/kafka/bin/kafka-configs.sh --bootstrap-server localhost:9092 --entity-type brokers --entity-name 1 --describe --all 2>/dev/null | grep -E 'log.retention.(hours|bytes)='"
```
