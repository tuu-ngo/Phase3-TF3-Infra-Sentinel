# Pitch Backlog - Performance Efficiency + Security

**Ngày lập:** 09/07/2026  
**Mục tiêu:** bản backlog dùng cho pitch cuối Tuần 1, tập trung vào hai trụ **Performance Efficiency** và **Security** trên hệ thống EKS đang chạy thật.  
**Phạm vi team:** Performance Efficiency + Security.  
**Nguồn bằng chứng:** live cluster `techx-corp-tf3`, namespace `techx-tf3`, `SLO.md`, `BUDGET.md`, `INCIDENT_HISTORY.md`, `ARCHITECTURE.md`, chart/runtime manifests.

---

## 1. Cách xếp ưu tiên

Theo `PITCH_GUIDE.md`:

```text
Ưu tiên = Rủi ro (khả năng xảy ra x mức nghiêm trọng) x Tác động business
```

Trong backlog này, business impact được quy về:

- **SLO:** checkout success rate >= 99.0%, browse/cart success rate >= 99.5%, storefront/frontend p95 < 1s.
- **Budget:** giới hạn khoảng 300 USD/tuần/TF, nên không tối ưu bằng cách tăng tài nguyên mù.
- **Incident history:** hệ thống từng lỗi do quá tải, thiếu replica/state, thiếu readiness khi deploy.
- **Architecture:** luồng ra tiền đi qua `frontend-proxy`, `frontend`, `checkout`, `cart`, `product-catalog`, `payment`; datastore chính là `postgresql`, `valkey-cart`, `kafka`.

---

## 2. Snapshot Security + Performance hiện tại

```text
Cluster: techx-corp-tf3
Region: ap-southeast-1
Namespace: techx-tf3
Kubernetes: 1.32
Node group: 3 x t3.large, min=3, desired=3, max=6
Ingress: frontend-proxy qua ALB internet-facing, HTTP/80
```

Điểm tốt:

- Các app chính đang Running.
- ECR repo `techx-corp` đã bật `scanOnPush=True`.
- App images có tag theo commit/build dạng `d2bc367-*`, tốt hơn tag `latest`.
- ServiceAccount `techx-corp` hiện chưa thấy quyền Kubernetes rộng khi kiểm `kubectl auth can-i --list`.
- Các service nội bộ đang là `ClusterIP`, chưa public trực tiếp Grafana/Jaeger/Postgres/Valkey/Kafka bằng Service type `LoadBalancer`.

Điểm rủi ro cần pitch:

```text
NetworkPolicy: No resources found
ResourceQuota: No resources found
LimitRange: No resources found
HPA: No resources found
Metrics API: kubectl top pods/nodes -> Metrics API not available
metrics-server / cluster-autoscaler / karpenter: NotFound
PVC: No resources found
Gần như mọi app deployment chính: replicas=1

SecurityContext live:
- 28 containers
- readOnlyRootFilesystem=0/28
- seccompProfile=0/28
- allowPrivilegeEscalation=false chỉ 4/28
- capabilities.drop chỉ 4/28

Namespace labels:
- chưa có pod-security.kubernetes.io/enforce|audit|warn

Identity:
- phần lớn app pod dùng chung serviceAccount techx-corp

Image supply chain:
- ECR scanOnPush=True
- imageTagMutability=MUTABLE
- workload pin theo tag, chưa pin digest
```

---

## 3. Top backlog đề xuất

| Rank | Item | Trụ | Vì sao đứng ở đây |
|---:|---|---|---|
| 1 | Chặn lateral movement bằng NetworkPolicy tối thiểu | Security | Có PoC thật: pod không cần datastore vẫn connect được Postgres/Valkey/Grafana; risk cao, fix chủ yếu là K8s config |
| 2 | Chốt public ingress boundary: CloudFront-only hay ALB public HTTP | Security | Ingress `frontend-proxy` đang ALB internet-facing HTTP/80; cần quyết định boundary public chính thức |
| 3 | Đưa Metrics API/`metrics-server` vào baseline vận hành | Performance | Không có metrics thì không thể chứng minh performance, HPA, right-size hay capacity plan |
| 4 | Đặt CPU/memory requests đúng cho critical services | Performance / Cost | Autoscaler/HPA cần requests; hiện nhiều service thiếu CPU request, `llm` BestEffort, memory limit thấp |
| 5 | Pod Security Standards + securityContext hardening | Security | 28 containers nhưng chưa có read-only root FS/seccomp; chỉ 4/28 chặn privilege escalation |
| 6 | ResourceQuota + LimitRange cho namespace | Performance / Cost / Reliability | Namespace chưa có guardrail; một workload lỗi có thể chiếm tài nguyên và làm lệch scheduler/cost |
| 7 | Thiết kế HPA + node autoscaling sau khi có metrics/requests | Performance / Cost | Node group max=6 nhưng chưa có workload/node autoscaling controller; traffic tăng vẫn chịu bằng capacity tĩnh |
| 8 | Image supply chain: tag immutability, digest pinning, scan gate | Security / Auditability | ECR scan-on-push đã bật nhưng tag vẫn mutable; workload chưa pin digest |
| 9 | Giảm service surface nội bộ: observability/datastore/load-generator ports | Security / Reliability | ClusterIP không public nhưng trong namespace không có NetworkPolicy; Jaeger/OpenSearch/Kafka/Postgres/Valkey mở nhiều port nội bộ |
| 10 | Workload identity hygiene: tách serviceAccount theo workload | Security / Auditability | App dùng chung serviceAccount `techx-corp`; hiện chưa quá quyền nhưng dễ privilege creep về sau |
| 11 | SLO/load-test evidence pack cho browse/cart/checkout | Performance / Auditability | Có SLO rõ nhưng thiếu bộ bằng chứng chuẩn: p95, success rate, CPU/memory, restart, events |
| 12 | Datastore backpressure: Postgres/Valkey/Kafka connection và queue pressure | Performance / Reliability | Scaling app có thể làm datastore nghẹt nếu không có pool/backpressure/connection ceiling |
| 13 | Topology spread/anti-affinity cho service critical | Performance / Reliability | Khi tăng replica, cần đảm bảo pod critical không dồn cùng node/AZ |
| 14 | Rollout evidence cho Security/Performance changes | Auditability | NetworkPolicy, HPA, quota, securityContext đều có thể làm gãy app nếu thiếu smoke test/rollback evidence |

---

## 4. Chi tiết từng backlog

### 1. Chặn lateral movement bằng NetworkPolicy tối thiểu

**Trụ:** Security  
**Priority:** P0

**Evidence thật**

```text
kubectl -n techx-tf3 get networkpolicy
-> No resources found

PoC đã ghi nhận:
image-provider -> postgresql:5432   open
image-provider -> valkey-cart:6379  open
image-provider -> grafana:80        open
```

Theo `ARCHITECTURE.md`:

```text
image-provider: phục vụ ảnh tĩnh, dependency chính: -
load-generator: sinh tải mô phỏng người dùng, dependency chính: frontend-proxy
postgresql: dùng bởi product-catalog, product-reviews, accounting
valkey-cart: dùng bởi cart
kafka: dùng bởi checkout, accounting, fraud-detection
```

**Risk**

Một service không cần datastore vẫn có thể đi ngang tới database/cache/observability. Đây là rủi ro security rõ nhất vì đã có PoC chạy được trên live cluster, không phải suy đoán.

**Business impact**

- Postgres chứa product catalog, reviews, accounting.
- Valkey chứa cart state, liên quan trực tiếp tới giỏ hàng.
- Grafana/observability bị truy cập sai có thể lộ trạng thái vận hành và giúp attacker hiểu hệ thống.
- Nếu datastore bị ảnh hưởng, checkout/cart SLO có thể bị kéo xuống.

**Chi phí/khả thi**

- Gần như không tốn thêm AWS cost vì dùng Kubernetes NetworkPolicy.
- Chi phí chính là map flow và smoke test để không tự chặn traffic hợp lệ.

**Đề xuất làm**

1. Không bật deny-all một phát vào toàn namespace.
2. Bắt đầu bằng policy bảo vệ datastore và observability:
   - Postgres chỉ cho `product-catalog`, `product-reviews`, `accounting`.
   - Valkey chỉ cho `cart`.
   - Kafka chỉ cho `checkout`, `accounting`, `fraud-detection`.
   - Grafana/Prometheus/Jaeger/OpenSearch chỉ cho đường quan sát cần thiết.
3. Test browse/cart/checkout/review sau mỗi policy.
4. Ghi rollback command cho từng policy.

**Acceptance criteria**

- `image-provider` không còn connect được Postgres/Valkey/Grafana.
- Browse/cart/checkout vẫn pass.
- Có policy allowlist theo flow trong `ARCHITECTURE.md`.
- Có rollback rõ cho từng policy.

---

### 2. Chốt public ingress boundary: CloudFront-only hay ALB public HTTP

**Trụ:** Security  
**Priority:** P0/P1

**Evidence thật**

```text
Ingress frontend-proxy:
alb.ingress.kubernetes.io/scheme: internet-facing
alb.ingress.kubernetes.io/listen-ports: [{"HTTP": 80}]
alb.ingress.kubernetes.io/target-type: ip
ingressClassName: alb

ALB hostname:
k8s-techxtf3-frontend-3153771b08-570141225.ap-southeast-1.elb.amazonaws.com
```

CloudFront HTTPS đã có trong hệ thống, nhưng ALB vẫn là endpoint public HTTP có thể gọi trực tiếp.

**Risk**

Nếu CloudFront là edge chính thức nhưng ALB public HTTP vẫn mở rộng, người dùng/attacker có thể bypass CloudFront policy, TLS edge, logging/routing mong muốn. Nếu ALB public là chủ đích trong giai đoạn test, vẫn cần ghi rõ quyết định và tradeoff.

**Business impact**

- Giảm public attack surface.
- Giúp team trả lời được: entrypoint chính thức là gì, TLS/logging/routing nằm ở đâu.
- Tránh cấu hình "vừa có CloudFront vừa để ALB public không rõ chủ đích".

**Đề xuất làm**

1. Ghi ADR ngắn: public entrypoint chính thức là CloudFront hay ALB.
2. Nếu CloudFront là entrypoint chính, restrict ALB source hoặc có cơ chế kiểm soát tương đương.
3. Không route public tới Grafana/Jaeger/Prometheus/OpenSearch.
4. Nếu ALB HTTP/80 là tạm thời cho test, ghi deadline review.

**Acceptance criteria**

- Có ADR/decision log cho edge boundary.
- `curl`/browser test xác nhận đường public chính thức.
- Không có route public tới observability/datastore.
- Security pitch giải thích được vì sao ALB public đang được chấp nhận hoặc đang được giới hạn.

---

### 3. Đưa Metrics API/`metrics-server` vào baseline vận hành

**Trụ:** Performance Efficiency  
**Priority:** P1, nhưng là dependency bắt buộc cho các task performance phía sau.

**Evidence thật**

```text
kubectl top nodes
-> Metrics API not available

kubectl -n techx-tf3 top pods
-> Metrics API not available

kubectl -n kube-system get deploy metrics-server
-> NotFound

v1beta1.metrics.k8s.io
-> NotFound
```

**Risk**

Không có metrics live thì không thể chứng minh:

- CPU/memory pressure theo pod/node.
- Right-size requests/limits.
- HPA.
- Capacity plan.
- Tác động của load test lên p95/success rate.

**Business impact**

SLO yêu cầu frontend p95 < 1s và success rate cho browse/cart/checkout. Không đo được thì không quản được, và mọi quyết định performance sẽ bị coi là cảm tính.

**Đề xuất làm**

1. Cài hoặc chuẩn hóa `metrics-server`.
2. Lưu evidence `kubectl top nodes/pods`.
3. Chạy baseline idle và baseline dưới load-generator.
4. Dùng metrics làm input cho right-size/HPA/quota.

**Acceptance criteria**

- `kubectl top nodes` trả số liệu cho 3 nodes.
- `kubectl -n techx-tf3 top pods` trả số liệu cho app/observability pods.
- Có snapshot CPU/memory idle và khi load.
- Right-size/HPA không được làm trước khi có baseline này.

---

### 4. Đặt CPU/memory requests đúng cho critical services

**Trụ:** Performance Efficiency / Cost  
**Priority:** P1

**Evidence thật**

```text
Grafana OOMKilled, memory limit 300Mi
Jaeger OOMKilled, memory limit/request 600Mi
product-catalog restart 3, memory limit/request 20Mi
llm QoS: BestEffort
Nhiều app thiếu CPU request
Một node đã khoảng 64% CPU requests, node khác thấp hơn
```

**Risk**

Scheduler và autoscaler không có tín hiệu đúng. Pod có thể bị pack quá dày, OOM, eviction, hoặc HPA scale sai. Đặt CPU limits cứng quá sớm cũng có thể gây throttling, nên bước đầu là request baseline.

**Business impact**

- Ảnh hưởng trực tiếp tới checkout/browse/cart SLO khi tải tăng.
- Giảm restart/OOM trong observability và service path.
- Giúp CFO thấy tăng/giảm tài nguyên dựa trên số liệu, không phải đoán.

**Đề xuất làm**

1. Sau khi có metrics, lập bảng usage/request/limit.
2. Ưu tiên `frontend-proxy`, `frontend`, `checkout`, `cart`, `product-catalog`, `payment`, `postgresql`, `valkey-cart`.
3. Đưa `llm` ra khỏi BestEffort.
4. Review các service memory thấp như `product-catalog`, `checkout`, `currency`, `shipping`.
5. Không đặt CPU limits cứng đại trà nếu chưa đo throttling.

**Acceptance criteria**

- Không còn pod critical QoS `BestEffort`.
- Grafana/Jaeger không OOMKilled trong phiên load test/quan sát.
- Có bảng request/limit theo service với lý do.
- Node allocation cân bằng hơn, không dồn request bất thường.

---

### 5. Pod Security Standards + securityContext hardening

**Trụ:** Security  
**Priority:** P1

**Evidence thật**

```text
Tổng containers trong deployment: 28
runAsNonRoot có set ở pod/container: 11/28
readOnlyRootFilesystem: 0/28
allowPrivilegeEscalation=false: 4/28
capabilities.drop có set: 4/28
seccompProfile có set: 0/28
privileged=true: 0/28

Namespace techx-tf3:
chưa có pod-security.kubernetes.io/enforce|audit|warn

Chart:
default.securityContext: {}
```

**Risk**

Chưa thấy container privileged, đây là điểm tốt. Nhưng workload chưa có baseline hardening đồng đều. Nếu một service bị khai thác, container có thể có filesystem ghi được, chưa drop capabilities mặc định, chưa có seccomp `RuntimeDefault`, và nhiều container chưa ép `runAsNonRoot`.

**Business impact**

- Giảm blast radius khi một container bị khai thác.
- Tăng điểm Security/Auditability.
- Cho thấy team hiểu security ở tầng pod runtime, không chỉ tầng network.

**Đề xuất làm**

1. Bật Pod Security Admission ở chế độ `audit/warn` trước.
2. Áp baseline securityContext cho stateless services:
   - `allowPrivilegeEscalation: false`
   - `capabilities.drop: ["ALL"]`
   - `seccompProfile.type: RuntimeDefault`
   - `runAsNonRoot: true` nếu image hỗ trợ
   - `readOnlyRootFilesystem: true` nếu app không cần ghi root FS
3. Test trước với `frontend`, `checkout`, `cart`, `currency`, `shipping`, `payment`.
4. Với Postgres/Kafka/Valkey/observability, kiểm tra path ghi trước khi bật read-only.

**Acceptance criteria**

- Namespace có PSA `audit`/`warn` ít nhất mức `baseline`.
- >=80% app containers có `allowPrivilegeEscalation=false`, `drop ALL`, `seccompProfile=RuntimeDefault`.
- Không có workload critical bị CrashLoop sau khi hardening.
- Có danh sách exception rõ cho image chưa hỗ trợ.

---

### 6. ResourceQuota + LimitRange cho namespace

**Trụ:** Performance / Cost / Reliability  
**Priority:** P1/P2

**Evidence thật**

```text
kubectl -n techx-tf3 get resourcequota
No resources found

kubectl -n techx-tf3 get limitrange
No resources found

Repo có mẫu:
phase3 - information/deploy/quota.yaml
```

**Risk**

Không có quota/limitrange nghĩa là namespace không có guardrail tài nguyên. Một deployment sai request/limit hoặc một load-generator cấu hình quá tay có thể chiếm tài nguyên, làm pod khác pending/evict/OOM, và làm cost/capacity khó kiểm soát.

**Business impact**

- Bảo vệ budget 300 USD/tuần/TF.
- Bảo vệ checkout path khỏi noisy-neighbor trong cùng namespace.
- Buộc workload mới khai báo request/limit tối thiểu.

**Đề xuất làm**

1. Không apply quota trước khi right-size cơ bản, vì quota sai có thể tự bóp workload.
2. Sau khi có Metrics API và request baseline, thêm `LimitRange`.
3. Thêm `ResourceQuota` theo tổng CPU/memory hợp lý với 3 node hiện tại.
4. Đặt exception hoặc quota riêng cho load test nếu cần.

**Acceptance criteria**

- Pod mới không thể chạy mà thiếu request/limit tối thiểu.
- Namespace có quota tổng không vượt capacity thực tế quá xa.
- Deploy fail sớm nếu resource khai báo vô lý.
- Load-generator không thể vô tình chiếm hết namespace budget.

---

### 7. Thiết kế HPA + node autoscaling sau khi có metrics/requests

**Trụ:** Performance Efficiency / Cost  
**Priority:** P1/P2

**Evidence thật**

```text
kubectl -n techx-tf3 get hpa
-> No resources found

cluster-autoscaler: NotFound
karpenter: NotFound
Node group: min=3, desired=3, max=6
Metrics API: not available
```

**Risk**

Traffic tăng thì app không tự scale. Nếu scale pod thủ công mà node thiếu capacity, pod sẽ Pending. Nếu cài autoscaler nhưng không có request/HPA đúng, hệ thống có thể scale sai hoặc tăng cost.

**Business impact**

- Bảo vệ checkout/browse/cart dưới peak traffic.
- Liên quan trực tiếp budget vì autoscaling sai có thể overpay.
- Giúp performance story có thứ tự trưởng thành: đo -> request -> HPA -> node autoscale.

**Đề xuất làm**

1. HPA cho stateless critical services sau Metrics API và requests.
2. Ưu tiên `frontend-proxy`, `frontend`, `checkout`, `cart`, `product-catalog`.
3. Chọn CPU metric trước nếu chưa có custom metric tốt.
4. Cài Cluster Autoscaler hoặc quyết định Karpenter bằng ADR.
5. Nếu muốn tiết kiệm thật, review `node_min_size`, không chỉ cài controller.

**Acceptance criteria**

- HPA tồn tại cho service critical.
- Khi load tăng, replicas tăng có kiểm soát.
- Khi load giảm, replicas giảm lại.
- Nếu pod Pending vì thiếu node, node autoscaling phản ứng đúng.

---

### 8. Image supply chain: tag immutability, digest pinning, scan gate

**Trụ:** Security / Auditability  
**Priority:** P1/P2

**Evidence thật**

```text
ECR repository: techx-corp
scanOnPush: True
imageTagMutability: MUTABLE
encryption: AES256

App images:
012619468490.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp:d2bc367-checkout
012619468490.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp:d2bc367-frontend
...

External images:
postgres:17.6
valkey/valkey, tag 9.0.1-alpine3.23
docker.io/grafana/grafana:13.0.1
jaegertracing/jaeger:2.17.0
quay.io/prometheus/prometheus:v3.11.3
```

**Risk**

Scan-on-push đã bật là điểm tốt. Nhưng tag vẫn mutable và workload pin theo tag, chưa pin digest. Nếu tag bị ghi đè hoặc external image đổi theo tag upstream, cluster có thể chạy artifact không đúng với bằng chứng review/rollback.

**Business impact**

- Bảo vệ auditability: image nào build, image nào deploy, scan kết quả gì.
- Giảm rủi ro supply-chain.
- Rollback chắc hơn vì rollback về digest cụ thể.

**Đề xuất làm**

1. Chuyển ECR `imageTagMutability` sang `IMMUTABLE` sau khi thống nhất release workflow.
2. Pin digest cho image quan trọng trong Helm values hoặc release manifest.
3. Lưu image digest trong release note/Helm history.
4. Thêm gate không deploy image có CRITICAL/HIGH vượt ngưỡng thống nhất.
5. Với external images, ghi version/digest và cadence review.

**Acceptance criteria**

- Release note có tag + digest cho image app.
- ECR tag không bị overwrite sau release.
- Có bằng chứng scan cho image đang chạy.
- Helm rollback không phụ thuộc tag có thể bị ghi đè.

---

### 9. Giảm service surface nội bộ: observability/datastore/load-generator ports

**Trụ:** Security / Reliability  
**Priority:** P2

**Evidence thật**

```text
Tất cả service trong namespace là ClusterIP, đây là điểm tốt.

Nhưng internal surface khá rộng:
jaeger: 5775/UDP, 5778/TCP, 6831/UDP, 6832/UDP, 9411/TCP,
        14250/TCP, 14267/TCP, 14268/TCP, 4317/TCP, 4318/TCP,
        16686/TCP, 16685/TCP, 8888/TCP, 8889/TCP
opensearch: 9200/TCP, 9300/TCP, 9600/TCP
kafka: 9092/TCP, 9093/TCP
postgresql: 5432/TCP
valkey-cart: 6379/TCP
load-generator: 8089/TCP
```

**Risk**

ClusterIP không public ra internet, nhưng trong namespace không có NetworkPolicy thì mọi pod vẫn có thể thử kết nối các port nội bộ. Observability và datastore thường chứa thông tin hữu ích cho attacker hoặc làm tăng khả năng phá hệ thống khi một pod bị compromise.

**Business impact**

- Giảm blast radius runtime.
- Bảo vệ datastore và observability evidence.
- Chứng minh team hiểu topology nội bộ, không chỉ entrypoint public.

**Đề xuất làm**

1. Dùng NetworkPolicy để giới hạn ai được gọi Jaeger/OpenSearch/Prometheus/Grafana.
2. Review xem `load-generator` có cần service port mở liên tục không.
3. Tách observability access theo label/serviceAccount.
4. Không xóa port bừa bãi nếu chart/operator cần; ưu tiên policy trước.

**Acceptance criteria**

- Pod app thường không gọi được Jaeger UI/OpenSearch/Grafana nếu không cần.
- Chỉ collector/observability components gọi được port ingest/metrics cần thiết.
- Load-generator không trở thành entrypoint nội bộ không kiểm soát.
- Smoke test telemetry vẫn ghi trace/metrics bình thường.

---

### 10. Workload identity hygiene: tách serviceAccount theo workload

**Trụ:** Security / Auditability  
**Priority:** P2

**Evidence thật**

```text
Hầu hết app pod dùng serviceAccount: techx-corp
Các service dùng chung: frontend, checkout, cart, payment, product-catalog,
product-reviews, kafka, postgresql, valkey-cart, load-generator, flagd...

kubectl auth can-i --as=system:serviceaccount:techx-tf3:techx-corp --list -n techx-tf3
=> không thấy quyền namespace rộng; chủ yếu là selfsubject review và non-resource get cơ bản
```

**Risk**

Điểm tốt là serviceAccount `techx-corp` hiện chưa có quyền rộng. Nhưng dùng chung identity cho gần như toàn bộ app khiến audit khó hơn. Khi sau này thêm quyền cho một workload, quyền đó có thể vô tình áp lên nhiều workload khác.

**Business impact**

- Giảm privilege creep.
- Audit rõ workload nào cần quyền gì.
- Hỗ trợ câu chuyện Security trưởng thành: không đợi quyền phình ra mới tách boundary.

**Đề xuất làm**

1. Tách serviceAccount theo nhóm:
   - `techx-frontend`
   - `techx-checkout`
   - `techx-data`
   - `techx-observability`
   - `techx-load-generator`
   - `techx-flagd`
2. Không cấp Role/RoleBinding nếu workload không cần Kubernetes API.
3. Ghi `kubectl auth can-i --list` làm evidence trước/sau.

**Acceptance criteria**

- App stateless không cần Kubernetes API chạy với serviceAccount riêng không có RoleBinding.
- Workload observability/data không dùng chung identity với app public path.
- Có bảng mapping service -> serviceAccount -> quyền cần thiết.

---

### 11. SLO/load-test evidence pack cho browse/cart/checkout

**Trụ:** Performance / Auditability  
**Priority:** P1/P2

**Evidence từ yêu cầu**

```text
checkout success rate >= 99.0%
browse/cart success rate >= 99.5%
frontend p95 latency < 1s
```

Cluster hiện có `load-generator`, Prometheus/Grafana/Jaeger, nhưng Grafana/Jaeger đang không ổn định và Metrics API chưa hoạt động.

**Risk**

Nếu không có evidence pack chuẩn, pitch performance sẽ rơi vào mô tả cảm tính. Team cần nói được: trước khi làm backlog, p95/success/restart/event như thế nào; sau khi làm, cải thiện ra sao.

**Business impact**

- Chứng minh backlog có tác động business.
- Giúp ưu tiên giữa tăng replica, tăng resource, HPA, persistence.
- Tạo bằng chứng cho postmortem/ADR.

**Đề xuất làm**

1. Chuẩn hóa kịch bản load nhẹ và spike.
2. Thu cùng lúc:
   - request rate
   - p95 latency
   - success rate
   - pod restarts
   - `kubectl get events`
   - CPU/memory pod/node
   - trace/error sample
3. Lưu evidence vào `docs/evidence/` hoặc appendix.
4. Dùng cùng kịch bản để compare trước-sau từng backlog.

**Acceptance criteria**

- Có evidence pack chạy lại được cho browse/cart/checkout.
- Có baseline trước khi thay đổi probes/replicas/resources.
- Có số liệu sau thay đổi để bảo vệ pitch.
- Nếu Grafana lỗi, vẫn có fallback bằng `kubectl`, Prometheus query hoặc log/event.

---

### 12. Datastore backpressure: Postgres/Valkey/Kafka connection và queue pressure

**Trụ:** Performance / Reliability  
**Priority:** P1/P2

**Evidence repo/runtime**

```text
product-catalog, product-reviews, accounting -> postgresql
cart -> valkey-cart
checkout -> kafka producer
accounting, fraud-detection -> kafka consumer
```

Các phát hiện kỹ thuật đã ghi trong repo:

- `product-catalog` dùng `database/sql` nhưng chưa set `MaxOpenConns`/`MaxIdleConns`.
- `product-reviews` mở `psycopg2.connect()` mới cho mỗi request.
- 3 service dùng chung một Postgres instance.
- Kafka chỉ có một broker trong namespace.
- Valkey chỉ có một instance cho cart.

**Risk**

Khi traffic tăng, bottleneck không nhất thiết nằm ở CPU app. Nó có thể nằm ở connection tới Postgres, queue Kafka, hoặc Valkey latency. Nếu app không có pool/backpressure/retry hợp lý, scaling pod có thể làm datastore nghẹt nhanh hơn.

**Business impact**

- Bảo vệ checkout/cart/catalog path.
- Tránh lặp lại kiểu sự cố quá tải giờ cao điểm.
- Giúp team không pitch "scale pod" như thuốc chữa mọi bệnh.

**Đề xuất làm**

1. Đặt connection pool ceiling cho `product-catalog`.
2. Thêm pool cho `product-reviews`.
3. Đo Postgres connection count/latency khi load.
4. Đo Kafka producer/consumer lag nếu có metric.
5. Đặt retry/backoff/circuit breaker ở service gọi datastore.
6. Không tăng replicas của service DB-heavy trước khi có trần connection.

**Acceptance criteria**

- Postgres không bị connection spike khi tăng load.
- `product-catalog` và `product-reviews` có pool/backpressure rõ.
- Load test checkout/cart/catalog không làm datastore chết trước app.
- Có dashboard/query theo dõi DB connection, Kafka lag, Valkey latency nếu stack hỗ trợ.

---

### 13. Topology spread/anti-affinity cho service critical

**Trụ:** Performance / Reliability  
**Priority:** P2

**Evidence thật**

```text
Cluster có 3 nodes Ready:
- ip-10-0-11-51
- ip-10-0-30-193
- ip-10-0-45-222

Chart default:
default.replicas: 1
default.schedulingRules.affinity: {}
```

**Risk**

Khi tăng replicas lên 2, nếu không có topology spread/anti-affinity, scheduler vẫn có thể đặt hai pod cùng node hoặc phân bố không tối ưu. Khi node đó có vấn đề, service vẫn có thể mất nhiều replica cùng lúc.

**Business impact**

- Tăng hiệu quả của việc scale replicas.
- Giảm node-level disruption ảnh hưởng checkout path.
- Giúp performance ổn định hơn vì workload critical phân tán tốt hơn.

**Đề xuất làm**

1. Làm sau khi tăng replicas cho checkout path.
2. Dùng `topologySpreadConstraints` theo hostname/zone cho `frontend-proxy`, `frontend`, `checkout`, `payment`, `cart`, `product-catalog`.
3. Dùng `preferredDuringSchedulingIgnoredDuringExecution` trước nếu sợ hard rule làm pod Pending.
4. Xác nhận phân bố bằng `kubectl get pods -o wide`.

**Acceptance criteria**

- Replica critical không dồn cùng một node nếu cluster còn capacity.
- Kill một pod/node trong test, service vẫn còn endpoint ready.
- Không tạo pending pod do rule quá cứng.
- Có output phân bố pod trước-sau.

---

### 14. Rollout evidence cho Security/Performance changes

**Trụ:** Auditability / Security / Performance  
**Priority:** P2

**Evidence thật**

- Helm release đã qua nhiều revision.
- `checkout` có nhiều ReplicaSet cũ.
- Các thay đổi như NetworkPolicy, quota, HPA, securityContext đều có thể làm gãy app nếu thiếu smoke test.

**Risk**

Security/Performance changes thường không tạo feature mới nhưng có blast radius lớn. Nếu apply policy/quota/HPA sai, hệ thống có thể lỗi mà team không có bằng chứng rollback rõ.

**Business impact**

- Tăng auditability cho Phase 3.
- Giảm MTTR nếu thay đổi hạ tầng gây lỗi.
- Giúp pitch có bằng chứng trưởng thành vận hành.

**Đề xuất làm**

1. Mỗi thay đổi Security/Performance phải có:
   - before evidence
   - command/change summary
   - after evidence
   - smoke test
   - rollback command
2. Lưu evidence cho NetworkPolicy, Metrics API, requests/limits, HPA, quota, securityContext.
3. Chuẩn hóa smoke test: browse/cart/checkout/observability.

**Acceptance criteria**

- Mỗi backlog P0/P1 có evidence trước-sau.
- Có rollback procedure cho policy/quota/HPA/securityContext.
- Team trả lời được "đổi gì, vì sao, kết quả thế nào, rollback ra sao".

---

## 5. Thứ tự triển khai đề xuất

### Trong 24-48h trước/sau pitch

1. **P0-1 NetworkPolicy phase 1:** chặn lateral movement tới Postgres/Valkey/Grafana.
2. **P0/P1-2 Ingress boundary:** chốt CloudFront/ALB public path bằng ADR.
3. **P1-3 Metrics API:** khôi phục `kubectl top`.
4. **P1-11 Evidence pack:** chuẩn hóa p95/success/restart/events/resource snapshot.

### Tuần 1

5. **P1-4 Resource requests:** right-size critical services, đưa `llm` khỏi BestEffort.
6. **P1-5 Pod Security hardening:** PSA audit/warn, securityContext cho stateless apps.
7. **P1/P2-6 ResourceQuota/LimitRange:** thêm guardrail sau khi có baseline request.
8. **P1/P2-12 Datastore backpressure:** connection pool/ceiling trước khi scale mạnh.

### Tuần 2-3

9. **P1/P2-7 HPA + node autoscaling:** sau metrics/requests.
10. **P1/P2-8 Image supply chain:** immutable tags, digest pinning, scan gate.
11. **P2-9 Service surface:** giới hạn observability/datastore/load-generator ports bằng policy.
12. **P2-10 Workload identity:** tách serviceAccount theo nhóm.
13. **P2-13 Topology spread:** phân tán replicas critical theo node/zone.
14. **P2-14 Rollout evidence:** chuẩn hóa evidence/rollback cho mọi thay đổi.

---

## 6. Việc cố ý chưa ưu tiên trong pitch này

| Việc | Vì sao chưa làm trước |
|---|---|
| Karpenter | Tốt nhưng quá sớm khi chưa có Metrics API, requests, HPA, PDB và cost baseline |
| Managed RDS/ElastiCache/MSK | Quan trọng nhưng là quyết định Reliability/Cost/ADR lớn, dễ vượt budget nếu không có mandate |
| WAF đầy đủ | Có giá trị security nhưng cần cost estimate; trước mắt chốt public boundary và giảm bypass path trước |
| Enforce NetworkPolicy deny-all toàn bộ ngay | Đúng hướng nhưng phải có allowlist và smoke test, nếu không tự làm gãy app |
| Enforce Pod Security `restricted` ngay | Có thể làm gãy workload legacy/polyglot; nên bắt đầu bằng `audit/warn` |
| CPU limits cứng cho mọi service | Có thể gây throttling nếu chưa có số liệu |
| Scale tất cả service lên 2 replicas | Tốn cost và có thể scale nhầm bottleneck; ưu tiên checkout path và datastore backpressure trước |

---

## 7. Narrative pitch 2 phút

```text
Team Performance Efficiency + Security không pitch rằng hệ thống đang chết. Cluster đang chạy, app chính Running, frontend-proxy public được qua ALB/CloudFront. Nhưng nếu nhìn theo SLO và incident history, rủi ro lớn hiện nằm ở hai lớp nền: security boundary và performance foundation.

Về Security, namespace hiện có 0 NetworkPolicy và đã có PoC cho thấy image-provider, một service không cần datastore, vẫn connect được Postgres, Valkey và Grafana. Pod Security cũng chưa đồng đều: 28 containers nhưng chưa có readOnlyRootFilesystem/seccomp, chỉ 4 containers chặn privilege escalation. ECR đã bật scan-on-push nhưng tag vẫn mutable. Nghĩa là hệ thống đang chạy được, nhưng blast radius nếu một pod bị lỗi hoặc bị khai thác còn rộng.

Về Performance, hiện kubectl top không chạy vì Metrics API chưa có, chưa có HPA, chưa có cluster-autoscaler, nhiều service thiếu CPU requests và llm đang BestEffort. Nếu chưa đo được CPU/memory/p95/success rate thì mọi quyết định right-size, HPA hay capacity plan đều là cảm tính.

Vì vậy thứ tự của team là: chặn lateral movement và chốt public ingress boundary trước; sau đó dựng metrics baseline, chuẩn hóa SLO evidence pack, right-size requests, rồi mới HPA/autoscaling. Các việc lớn hơn như Karpenter, managed database hay WAF đầy đủ được defer vì cần số liệu, ADR và cost estimate trước.
```

---

## 8. Evidence commands đã dùng

```text
kubectl cluster-info
kubectl get nodes -o wide
kubectl describe nodes
kubectl -n techx-tf3 get pods -o wide
kubectl -n techx-tf3 get deploy,rs,svc,ingress,hpa,pdb,resourcequota,limitrange,pvc -o wide
kubectl -n techx-tf3 get svc -o wide
kubectl -n techx-tf3 get ingress frontend-proxy -o yaml
kubectl -n techx-tf3 get networkpolicy
kubectl -n techx-tf3 get endpoints -o wide
kubectl -n techx-tf3 get events --sort-by=.lastTimestamp
kubectl -n techx-tf3 top pods
kubectl top nodes
kubectl -n kube-system get pods,deploy,ds,svc -o wide
kubectl -n kube-system get deploy cluster-autoscaler metrics-server karpenter -o wide
kubectl -n techx-tf3 get serviceaccount,role,rolebinding -o wide
kubectl -n techx-tf3 get pods -o custom-columns=NAME:.metadata.name,SA:.spec.serviceAccountName,NODE:.spec.nodeName --no-headers
kubectl get ns techx-tf3 -o jsonpath='{.metadata.labels}'
kubectl auth can-i --as=system:serviceaccount:techx-tf3:techx-corp --list -n techx-tf3
kubectl -n techx-tf3 get deploy -o json
aws eks describe-cluster --name techx-corp-tf3 --region ap-southeast-1
aws eks describe-nodegroup --cluster-name techx-corp-tf3 --nodegroup-name default-2026070708300555940000001a --region ap-southeast-1
aws ecr describe-repositories --repository-names techx-corp --region ap-southeast-1
aws elbv2 describe-target-health --region ap-southeast-1 --target-group-arn <frontend-proxy-tg>
```
