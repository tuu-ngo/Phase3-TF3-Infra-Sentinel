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

**Cập nhật 10/07/2026 — đã sửa lại thứ tự Rank 2-4:** bản trước xếp theo cảm tính pha lẫn thứ tự "cái gì làm trước về kỹ thuật", chưa đúng thuần công thức ở mục 1 (Rủi ro × Tác động business). Tính lại: mục #4 (CPU/memory requests) chứa bằng chứng **Grafana/Jaeger đang OOMKilled lặp lại thật** (không phải rủi ro lý thuyết — đã xảy ra, đo được số restart) nên phải xếp cao hơn mục #2 (Ingress boundary), vốn là rủi ro thật nhưng **chưa có bằng chứng bị khai thác**. Một sự cố đang diễn ra sống luôn ưu tiên hơn một rủi ro tiềm năng, dù severity/business impact lý thuyết của rủi ro tiềm năng có thể cao hơn. Cột **Mã #** giữ nguyên số thứ tự gốc ở Mục 4 để không phá link tham chiếu — chỉ **Rank** đổi.

| Rank | Mã # | Item | Trụ | Vì sao đứng ở đây |
|---:|---|---|---|---|
| 1 | #1 | Chặn lateral movement bằng NetworkPolicy tối thiểu | Security | Có PoC thật: pod không cần datastore vẫn connect được Postgres/Valkey/Grafana; risk cao, fix chủ yếu là K8s config |
| 2 | #4 | Đặt CPU/memory requests đúng cho critical services | Performance / Cost | **Đang là sự cố sống, không phải rủi ro** — Grafana/Jaeger OOMKilled lặp lại thật (verify: 11 + 6 lần restart); autoscaler/HPA cũng cần requests đúng để hoạt động |
| 3 | #3 | Đưa Metrics API/`metrics-server` vào baseline vận hành | Performance | Không có metrics thì không thể chứng minh performance, HPA, right-size hay capacity plan; chặn domino toàn bộ mục Performance phía sau |
| 4 | #2 | Chốt public ingress boundary: CloudFront-only hay ALB public HTTP | Security | Ingress `frontend-proxy` đang ALB internet-facing HTTP/80; rủi ro thật nhưng ở mức phòng ngừa, chưa có bằng chứng bị khai thác |
| 5 | #5 | Pod Security Standards + securityContext hardening | Security | 28 containers nhưng chưa có read-only root FS/seccomp; chỉ 4/28 chặn privilege escalation — lớp giảm nhẹ hậu quả, đứng sau lớp ngăn chặn đầu vào (#1, #2) |
| 6 | #6 | ResourceQuota + LimitRange cho namespace | Performance / Cost / Reliability | Namespace chưa có guardrail; một workload lỗi có thể chiếm tài nguyên và làm lệch scheduler/cost — nên làm ngay sau khi có request baseline từ #4 |
| 7 | #7 | Thiết kế HPA + node autoscaling sau khi có metrics/requests | Performance / Cost | Node group max=6 nhưng chưa có workload/node autoscaling controller; traffic hiện tại còn thấp nên chưa khẩn, nhưng cần làm nền cho tương lai |
| 8 | #8 | Image supply chain: tag immutability, digest pinning, scan gate | Security / Auditability | ECR scan-on-push đã bật nhưng tag vẫn mutable; workload chưa pin digest |
| 9 | #9 | Giảm service surface nội bộ: observability/datastore/load-generator ports | Security / Reliability | ClusterIP không public nhưng trong namespace không có NetworkPolicy; Jaeger/OpenSearch/Kafka/Postgres/Valkey mở nhiều port nội bộ |
| 10 | #10 | Workload identity hygiene: tách serviceAccount theo workload | Security / Auditability | App dùng chung serviceAccount `techx-corp`; hiện chưa quá quyền nhưng dễ privilege creep về sau |
| 11 | #11 | SLO/load-test evidence pack cho browse/cart/checkout | Performance / Auditability | **Là công cụ đo lường (enabler), không tự giảm rủi ro** — chỉ có giá trị khi dùng số liệu để quyết định việc khác (vd #7); không nên coi ngang hàng các mục tự thân giảm rủi ro |
| 12 | #12 | Datastore backpressure: Postgres/Valkey/Kafka connection và queue pressure | Performance / Reliability | Scaling app có thể làm datastore nghẹt nếu không có pool/backpressure/connection ceiling — **đáng cân nhắc nâng hạng** khi có thời gian rà lại kỹ hơn theo đúng công thức (chưa làm rigorous như Rank 1-7) |
| 13 | #13 | Topology spread/anti-affinity cho service critical | Performance / Reliability | Khi tăng replica, cần đảm bảo pod critical không dồn cùng node/AZ — hiện hầu hết service còn 1 replica nên giá trị mục này chưa hiện rõ |
| 14 | #14 | Rollout evidence cho Security/Performance changes | Auditability | NetworkPolicy, HPA, quota, securityContext đều có thể làm gãy app nếu thiếu smoke test/rollback evidence — là quy trình áp dụng cho mọi mục khác, không phải 1 fix riêng |
| 15 | #15 | Chuẩn hóa private access UX cho internal tools | Security / Auditability / Operations | SSM bastion + port-forward đạt least-exposure nhanh nhưng onboarding nhiều bước, khó vận hành cho nhiều team; cần backlog đánh giá VPN/Zero Trust và private domain |

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

**Ảnh hưởng khách hàng**

Đường đi PoC (`image-provider → postgresql/valkey-cart/grafana`) chạm tới 3 lớp: dữ liệu catalog/reviews/accounting (Postgres), state giỏ hàng thật của khách (Valkey), và trạng thái vận hành (Grafana). Nếu một service ít quan trọng bị khai thác trước, kẻ tấn công có thể đi ngang tới cart/checkout data — rủi ro không chỉ downtime mà còn sai lệch đơn hàng/giỏ hàng của khách đang mua.

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

**Rollback / nếu làm sai**

`kubectl -n techx-tf3 delete networkpolicy <tên-policy>` — revert tức thì (<5s), traffic quay lại trạng thái cũ. Luôn tự test bằng `kubectl exec` từ 1 pod đại diện (vd `image-provider`) gọi thử Postgres/Valkey/Grafana ngay sau khi áp mỗi policy để phát hiện lỗi trong <2 phút, không đợi khách hàng report lỗi trước.

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

**Ảnh hưởng khách hàng**

Nếu ALB public HTTP/80 vẫn mở song song CloudFront, khách hàng có thể vô tình (hoặc bị dẫn dụ qua link cũ/scan) truy cập thẳng qua ALB, bỏ qua lớp TLS/HTTPS mà CloudFront cung cấp — request/response truyền không mã hóa trên đường public, tăng rủi ro lộ session/thông tin đơn hàng.

**Risk**

Nếu CloudFront là edge chính thức nhưng ALB public HTTP vẫn mở rộng, người dùng/attacker có thể bypass CloudFront policy, TLS edge, logging/routing mong muốn. Nếu ALB public là chủ đích trong giai đoạn test, vẫn cần ghi rõ quyết định và tradeoff.

**Business impact**

- Giảm public attack surface.
- Giúp team trả lời được: entrypoint chính thức là gì, TLS/logging/routing nằm ở đâu.
- Tránh cấu hình "vừa có CloudFront vừa để ALB public không rõ chủ đích".

**Chi phí/khả thi**

Ghi ADR + review Ingress annotation không tốn chi phí AWS trực tiếp. Nếu quyết định restrict ALB source (vd Security Group chỉ cho phép dải IP CloudFront, hoặc custom header xác thực origin), effort ước 0.5 ngày-người, không cần thêm managed service.

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

**Rollback / nếu làm sai**

Nếu restrict ALB source sai làm CloudFront không gọi được origin (mất toàn bộ truy cập storefront), gỡ ngay rule/annotation restrict vừa thêm (revert Security Group hoặc `alb.ingress.kubernetes.io/*` annotation về giá trị cũ qua Helm/Terraform nếu quản lý bằng IaC). Test lại `curl` qua domain CloudFront ngay sau rollback để xác nhận phục hồi truy cập.

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

**Ảnh hưởng khách hàng**

Gián tiếp — khách hàng không thấy ngay khi thiếu metrics, nhưng team mất khả năng phát hiện sớm pod sắp OOM/CPU throttle trước khi nó thành sự cố chạm tới checkout/browse (xem mục #4). Không có metrics nghĩa là incident chỉ được phát hiện SAU khi khách hàng đã gặp lỗi, không phải trước.

**Risk**

Không có metrics live thì không thể chứng minh:

- CPU/memory pressure theo pod/node.
- Right-size requests/limits.
- HPA.
- Capacity plan.
- Tác động của load test lên p95/success rate.

**Business impact**

SLO yêu cầu frontend p95 < 1s và success rate cho browse/cart/checkout. Không đo được thì không quản được, và mọi quyết định performance sẽ bị coi là cảm tính.

**Chi phí/khả thi**

Cài `metrics-server` là thao tác chuẩn (`helm install`/manifest có sẵn), ước ~1-2 giờ-người bao gồm verify; không phát sinh chi phí AWS đáng kể (metrics-server chạy nhẹ, không cần managed service riêng).

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

**Rollback / nếu làm sai**

`helm uninstall metrics-server -n kube-system` (hoặc xoá manifest tương ứng) — an toàn gần như tuyệt đối, vì metrics-server không nằm trên request path của khách hàng (checkout/cart/browse không phụ thuộc nó để phục vụ request), rollback không ảnh hưởng traffic thật.

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

Bổ sung verify sống 10/07/2026 (qua SSM tunnel): Grafana **11 lần restart** (lần cuối 6h32m trước lúc verify), Jaeger **6 lần restart** — OOM lặp lại theo chu kỳ ~1h44p/lần dù đã set `GOMEMLIMIT`. `helm history` cho thấy revision 5 từng **failed** khi thử tăng `requests.memory=512Mi` mà quên tăng `limits.memory` theo (Helm từ chối patch); revision 6 **revert về 250Mi/300Mi** — vấn đề vẫn CHƯA được sửa qua nhiều lần upgrade sau đó.

**Ảnh hưởng khách hàng**

Grafana/Jaeger OOM lặp lại đúng lúc cần nhất làm mất khả năng quan sát — nếu checkout lỗi trùng thời điểm Jaeger đang restart, team **không có trace để debug**, kéo dài MTTR, khách hàng chịu downtime lâu hơn thực tế cần thiết. `product-catalog` restart (mem limit 20Mi) gây gián đoạn ngắn browse/search do chỉ có 1 replica, không có standby nhận traffic khi pod đang restart.

**Risk**

Scheduler và autoscaler không có tín hiệu đúng. Pod có thể bị pack quá dày, OOM, eviction, hoặc HPA scale sai. Đặt CPU limits cứng quá sớm cũng có thể gây throttling, nên bước đầu là request baseline.

**Business impact**

- Ảnh hưởng trực tiếp tới checkout/browse/cart SLO khi tải tăng.
- Giảm restart/OOM trong observability và service path.
- Giúp CFO thấy tăng/giảm tài nguyên dựa trên số liệu, không phải đoán.

**Chi phí/khả thi**

Không phát sinh chi phí AWS đáng kể (chỉ điều chỉnh config, không tăng node). Ước 2h cho phần Grafana/Jaeger khẩn cấp (không cần chờ metrics-server — evidence OOM đã có sẵn qua `kubectl events`), 1 ngày-người cho phần lập bảng + right-size toàn bộ ~8-10 service ưu tiên (cần metrics-server trước).

**Đề xuất làm**

1. **(Làm ngay, không cần chờ metrics-server)** Grafana: tăng cả `requests.memory` và `limits.memory` **cùng lúc** lên 400-512Mi, theo dõi ~2h. Jaeger: thêm `GOMEMLIMIT` khớp `limits.memory`.
2. Sau khi có metrics, lập bảng usage/request/limit.
3. Ưu tiên `frontend-proxy`, `frontend`, `checkout`, `cart`, `product-catalog`, `payment`, `postgresql`, `valkey-cart`.
4. Đưa `llm` ra khỏi BestEffort.
5. Review các service memory thấp như `product-catalog`, `checkout`, `currency`, `shipping`.
6. Không đặt CPU limits cứng đại trà nếu chưa đo throttling.

**Acceptance criteria**

- Không còn pod critical QoS `BestEffort`.
- Grafana/Jaeger không OOMKilled trong ít nhất 4h liên tục quan sát.
- Có bảng request/limit theo service với lý do.
- Node allocation cân bằng hơn, không dồn request bất thường.
- Helm upgrade cho Grafana/Jaeger chạy thành công, không failed như revision 5.

**Rollback / nếu làm sai**

`helm rollback techx-corp <revision-trước> -n techx-tf3`, hoặc riêng lẻ `kubectl -n techx-tf3 set resources deployment/grafana --requests=memory=250Mi --limits=memory=300Mi` để quay số cũ. **Bài học đã có sẵn:** luôn đổi `requests.memory` và `limits.memory` cùng lúc trong 1 lần upgrade — revision 5 đã fail vì chỉ đổi request mà quên limit.

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

Verify sống 10/07/2026 — ⚠️ số liệu đã lệch nhẹ, cần xác nhận trước khi dùng: tổng container hiện tại 29 (tăng 1), `seccompProfile` set 4/29 (gốc ghi 0/28 — có tín hiệu ai đó đã sửa 1 phần), `capabilities.drop` ALL 5/29 (gốc 4/28). Rủi ro cốt lõi vẫn nguyên: 0/29 `readOnlyRootFilesystem`, namespace vẫn chưa có PSA.

**Ảnh hưởng khách hàng**

Nếu một container bị khai thác (vd qua lỗ hổng dependency), do hầu hết chưa có `readOnlyRootFilesystem`/seccomp/drop-capabilities, kẻ tấn công có blast radius rộng hơn bình thường — có thể ghi file vào container, leo quyền dễ hơn. Vì nhiều service nằm ngay trên luồng ra tiền (`checkout`/`cart`/`payment`), một container bị chiếm có thể trở thành bàn đạp tới dữ liệu/luồng thanh toán của khách.

**Risk**

Chưa thấy container privileged, đây là điểm tốt. Nhưng workload chưa có baseline hardening đồng đều. Nếu một service bị khai thác, container có thể có filesystem ghi được, chưa drop capabilities mặc định, chưa có seccomp `RuntimeDefault`, và nhiều container chưa ép `runAsNonRoot`.

**Business impact**

- Giảm blast radius khi một container bị khai thác.
- Tăng điểm Security/Auditability.
- Cho thấy team hiểu security ở tầng pod runtime, không chỉ tầng network.

**Chi phí/khả thi**

Không tốn chi phí AWS. Ước 1-1.5 ngày-người để áp cho nhóm service ưu tiên + thời gian theo dõi CrashLoop sau mỗi lần áp.

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

**Rollback / nếu làm sai**

Nếu bật securityContext làm 1 service CrashLoop: `helm rollback techx-corp <revision-trước> -n techx-tf3`, hoặc gỡ riêng field securityContext vừa thêm cho service đó qua `kubectl edit deployment`. Test theo nhóm nhỏ trước (frontend/checkout/cart trước, datastore sau), phát hiện lỗi trong vài phút nhờ theo dõi CrashLoopBackOff ngay sau mỗi lần áp.

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

Verify sống 10/07/2026: vẫn `No resources found` cho cả resourcequota và limitrange, khớp 100% evidence gốc, chưa gì thay đổi.

**Ảnh hưởng khách hàng**

Nếu 1 workload (kể cả vô tình — ví dụ tăng Users của `load-generator` quá cao khi làm mục #11) chiếm hết CPU/memory namespace, các pod trên đúng luồng checkout/cart có thể bị đói tài nguyên, Pending, hoặc bị evict — gây gián đoạn trực tiếp cho khách đang mua hàng.

**Risk**

Không có quota/limitrange nghĩa là namespace không có guardrail tài nguyên. Một deployment sai request/limit hoặc một load-generator cấu hình quá tay có thể chiếm tài nguyên, làm pod khác pending/evict/OOM, và làm cost/capacity khó kiểm soát.

**Business impact**

- Bảo vệ budget 300 USD/tuần/TF.
- Bảo vệ checkout path khỏi noisy-neighbor trong cùng namespace.
- Buộc workload mới khai báo request/limit tối thiểu.

**Chi phí/khả thi**

Không tốn chi phí AWS trực tiếp — chỉ là config K8s. Ước 0.5 ngày-người, làm ngay sau khi có request baseline từ mục #4.

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

**Rollback / nếu làm sai**

`kubectl -n techx-tf3 delete resourcequota <tên>` / `kubectl -n techx-tf3 delete limitrange <tên>` — revert tức thì, không ảnh hưởng pod đang chạy (quota chỉ chặn pod MỚI được tạo vượt hạn mức, không giết pod cũ đang phục vụ traffic).

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

Verify sống 10/07/2026: `get hpa` vẫn `No resources found`.

**Ảnh hưởng khách hàng**

Traffic tăng đột biến (campaign, giờ cao điểm) mà không auto-scale → p95 latency vượt SLO (<1s) hoặc request timeout/error, ảnh hưởng trực tiếp nếu xảy ra trên checkout path (mất đơn thật, không chỉ trải nghiệm xấu).

**Risk**

Traffic tăng thì app không tự scale. Nếu scale pod thủ công mà node thiếu capacity, pod sẽ Pending. Nếu cài autoscaler nhưng không có request/HPA đúng, hệ thống có thể scale sai hoặc tăng cost.

**Business impact**

- Bảo vệ checkout/browse/cart dưới peak traffic.
- Liên quan trực tiếp budget vì autoscaling sai có thể overpay.
- Giúp performance story có thứ tự trưởng thành: đo -> request -> HPA -> node autoscale.

**Chi phí/khả thi**

HPA tầng pod không phát sinh cost trực tiếp. Cluster Autoscaler/Karpenter có thể phát sinh cost nếu scale node quá tay — review `node_min_size` trước. Ước 0.5 ngày-người cho HPA, 1 ngày-người cho quyết định + cài autoscaler (gồm viết ADR). Lưu ý (verify 10/07/2026): checkout hiện chỉ ~0.064 req/s — traffic thật chưa tạo áp lực cần autoscale ngay, nên đây là mục làm nền cho tương lai chứ không phải cấp cứu.

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

**Rollback / nếu làm sai**

`kubectl -n techx-tf3 delete hpa <tên>` — lưu ý: replicas **giữ nguyên ở mức cuối cùng** trước khi xoá, không tự về 1; cần `kubectl scale deploy <tên> --replicas=1` thủ công nếu muốn về trạng thái gốc. Tránh xoá HPA giữa lúc đang scale-up thật.

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
valkey/valkey:9.0.1-alpine3.23
docker.io/grafana/grafana:13.0.1
jaegertracing/jaeger:2.17.0
quay.io/prometheus/prometheus:v3.11.3
```

**Ảnh hưởng khách hàng**

Nếu tag bị ghi đè (do MUTABLE) hoặc external image thay đổi âm thầm theo tag upstream, khách hàng có thể vô tình chạy phải 1 phiên bản code chưa được test/scan — rủi ro chủ yếu là gián tiếp (không lộ dữ liệu ngay) nhưng làm giảm khả năng truy vết khi có sự cố xảy ra thật (không biết chính xác code nào đang chạy lúc khách hàng gặp lỗi).

**Risk**

Scan-on-push đã bật là điểm tốt. Nhưng tag vẫn mutable và workload pin theo tag, chưa pin digest. Nếu tag bị ghi đè hoặc external image đổi theo tag upstream, cluster có thể chạy artifact không đúng với bằng chứng review/rollback.

**Business impact**

- Bảo vệ auditability: image nào build, image nào deploy, scan kết quả gì.
- Giảm rủi ro supply-chain.
- Rollback chắc hơn vì rollback về digest cụ thể.

**Chi phí/khả thi**

Chuyển ECR sang IMMUTABLE không tốn chi phí AWS thêm. Digest pinning trong Helm values là thay đổi nhỏ, ước 0.5 ngày-người để làm cho toàn bộ image app + cập nhật release process.

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

**Rollback / nếu làm sai**

Nếu chuyển IMMUTABLE gây lỗi CI/CD (không build lại được tag cũ), revert lại MUTABLE qua `aws ecr put-image-tag-mutability`. Digest pinning sai thì sửa lại giá trị digest trong Helm values rồi `helm upgrade` lại.

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

**Ảnh hưởng khách hàng**

Gián tiếp — nếu 1 pod bị compromise qua 1 lỗ hổng khác, việc quan sát/datastore mở rộng port nội bộ giúp kẻ tấn công dễ khám phá và tấn công tiếp sang Jaeger/OpenSearch/Kafka/Postgres/Valkey hơn, kéo dài thời gian kẻ tấn công ở trong hệ thống trước khi bị phát hiện — làm tăng khả năng cuối cùng chạm tới dữ liệu/luồng thanh toán của khách.

**Risk**

ClusterIP không public ra internet, nhưng trong namespace không có NetworkPolicy thì mọi pod vẫn có thể thử kết nối các port nội bộ. Observability và datastore thường chứa thông tin hữu ích cho attacker hoặc làm tăng khả năng phá hệ thống khi một pod bị compromise.

**Business impact**

- Giảm blast radius runtime.
- Bảo vệ datastore và observability evidence.
- Chứng minh team hiểu topology nội bộ, không chỉ entrypoint public.

**Chi phí/khả thi**

Dùng lại đúng cơ chế NetworkPolicy của mục #1, không tốn thêm chi phí AWS. Effort chủ yếu là rà soát danh sách port cần thiết cho từng observability component — ước 0.5-1 ngày-người, làm sau khi mục #1 đã ổn định.

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

**Rollback / nếu làm sai**

`kubectl -n techx-tf3 delete networkpolicy <tên>` — giống mục #1, revert tức thì (<5s), traffic quay lại trạng thái cũ.

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

**Ảnh hưởng khách hàng**

Rất gián tiếp lúc này (serviceAccount `techx-corp` hiện chưa có quyền rộng) — rủi ro chính là về sau: khi có ai thêm quyền cho 1 workload cụ thể mà vô tình cấp luôn cho toàn bộ workload dùng chung identity, làm tăng bề mặt tấn công mà không ai nhận ra ngay, có thể ảnh hưởng gián tiếp tới mọi service trên luồng ra tiền.

**Risk**

Điểm tốt là serviceAccount `techx-corp` hiện chưa có quyền rộng. Nhưng dùng chung identity cho gần như toàn bộ app khiến audit khó hơn. Khi sau này thêm quyền cho một workload, quyền đó có thể vô tình áp lên nhiều workload khác.

**Business impact**

- Giảm privilege creep.
- Audit rõ workload nào cần quyền gì.
- Hỗ trợ câu chuyện Security trưởng thành: không đợi quyền phình ra mới tách boundary.

**Chi phí/khả thi**

Tạo thêm serviceAccount không tốn chi phí AWS. Effort chủ yếu là refactor Helm chart để mỗi nhóm workload dùng serviceAccount riêng — ước 1 ngày-người, nên làm sau các mục P0/P1 khác vì chưa có quyền rộng thật sự cần thu hẹp ngay.

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

**Rollback / nếu làm sai**

Đổi lại `serviceAccountName` trong Helm values về `techx-corp` chung, `helm upgrade` lại — an toàn vì không đổi quyền, chỉ đổi tên định danh.

---

### 11. SLO/load-test evidence pack cho browse/cart/checkout

> **Lưu ý khi xếp hạng:** đây là công cụ **đo lường/enabler**, không tự nó giảm rủi ro nào — khác các mục #1, #5, #6 là guardrail tự thân có tác dụng ngay khi làm xong. Giá trị của mục này chỉ hiện ra khi số liệu được dùng để quyết định việc khác (vd mục #7 — HPA). Khi pitch, có thể trình bày như điều kiện verify của #7 thay vì 1 mục độc lập ngang hàng.

**Trụ:** Performance / Auditability  
**Priority:** P1/P2

**Evidence từ yêu cầu**

```text
checkout success rate >= 99.0%
browse/cart success rate >= 99.5%
frontend p95 latency < 1s
```

Cluster hiện có `load-generator`, Prometheus/Grafana/Jaeger, nhưng Grafana/Jaeger đang không ổn định và Metrics API chưa hoạt động.

Verify sống 10/07/2026 (qua SSM tunnel + port-forward Prometheus): query checkout success rate chạy đúng, kết quả = **1 (100%)**, nhưng call rate chỉ **~0.064 req/s** — không đủ traffic để kết luận gì đáng tin về khả năng chịu tải thật.

**Ảnh hưởng khách hàng**

Bản thân việc tạo baseline không ảnh hưởng khách hàng nếu làm đúng cách, nhưng có rủi ro tự gây outage: trọng số traffic thật của `load-generator` (đọc từ `locustfile.py`) cho thấy `checkout`+`checkout_multi` chỉ ~6% traffic (dominant là `browse_product` ~31%) — muốn đo đủ RPS checkout phải tăng Users lên rất cao (100-300+). Nếu chạy mức tải này trùng lúc cluster đang phục vụ traffic thật khác, có thể tự gây outage.

**Risk**

Nếu không có evidence pack chuẩn, pitch performance sẽ rơi vào mô tả cảm tính. Team cần nói được: trước khi làm backlog, p95/success/restart/event như thế nào; sau khi làm, cải thiện ra sao.

**Business impact**

- Chứng minh backlog có tác động business.
- Giúp ưu tiên giữa tăng replica, tăng resource, HPA, persistence.
- Tạo bằng chứng cho postmortem/ADR.

**Chi phí/khả thi**

Không phát sinh chi phí AWS trực tiếp ngoài thời gian chạy tải. Ước 0.5-1 ngày-người để chuẩn hóa kịch bản + chạy + export evidence, phụ thuộc mục #3 (metrics-server) đã xong trước.

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

**Rollback / nếu làm sai**

Load test không đổi code/infra nên "rollback" = dừng tải ngay: `kubectl -n techx-tf3 scale deploy load-generator --replicas=0`, hoặc set Users=0 qua UI load-generator. Phát hiện sai trong <1 phút nếu theo dõi Grafana/Prometheus trong lúc chạy.

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

**Ảnh hưởng khách hàng**

Postgres `max_connections=100`, hiện dùng ~6 — còn dư nhiều, NHƯNG khi traffic tăng (đặc biệt nếu scale `product-catalog`/`product-reviews` theo mục #7-HPA) mà không có trần connection, có thể tự làm cạn pool Postgres **dùng chung** với `accounting`. Hậu quả không chỉ 1 service lỗi: browse (product-catalog), reviews, VÀ ghi sổ đơn hàng (accounting) có thể sập cùng lúc vì chung 1 Postgres instance.

**Risk**

Khi traffic tăng, bottleneck không nhất thiết nằm ở CPU app. Nó có thể nằm ở connection tới Postgres, queue Kafka, hoặc Valkey latency. Nếu app không có pool/backpressure/retry hợp lý, scaling pod có thể làm datastore nghẹt nhanh hơn.

**Business impact**

- Bảo vệ checkout/cart/catalog path.
- Tránh lặp lại kiểu sự cố quá tải giờ cao điểm.
- Giúp team không pitch "scale pod" như thuốc chữa mọi bệnh.

**Chi phí/khả thi**

Đây là thay đổi code (không phải config runtime), cần qua CI/CD build lại image — ước 0.5 ngày-người cho `product-catalog` (Go, chỉ thêm vài dòng `SetMaxOpenConns`), 1 ngày-người cho `product-reviews` (Python, cần đổi cách quản lý connection). Không phát sinh chi phí AWS.

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

**Rollback / nếu làm sai**

Vì là thay đổi code, rollback bằng deploy lại image tag ECR trước đó (`helm rollback` hoặc trỏ lại tag cũ) chứ không sửa được tức thời bằng `kubectl edit`. Vì cần build lại qua CI/CD, thời gian phát hiện sai chậm hơn các mục config-only khác — khuyến nghị test qua port-forward/staging trước khi merge.

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

**Ảnh hưởng khách hàng**

Rất gián tiếp lúc này — vì hầu hết service đang chạy 1 replica (đây chính là SPOF thật ghi trong `INCIDENT_HISTORY.md`), topology spread CHƯA áp dụng được cho tới khi tăng replicas trước (thuộc trụ Reliability, CDO02). Giá trị của mục này chỉ hiện rõ SAU khi replicas tăng lên ≥2.

**Risk**

Khi tăng replicas lên 2, nếu không có topology spread/anti-affinity, scheduler vẫn có thể đặt hai pod cùng node hoặc phân bố không tối ưu. Khi node đó có vấn đề, service vẫn có thể mất nhiều replica cùng lúc.

**Business impact**

- Tăng hiệu quả của việc scale replicas.
- Giảm node-level disruption ảnh hưởng checkout path.
- Giúp performance ổn định hơn vì workload critical phân tán tốt hơn.

**Chi phí/khả thi**

Không tốn chi phí AWS, chỉ là cấu hình scheduling. Ước 0.5 ngày-người, làm sau khi tăng replicas cho checkout path (phụ thuộc CDO02).

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

**Rollback / nếu làm sai**

Gỡ `topologySpreadConstraints` khỏi Helm values, `helm upgrade` lại — không ảnh hưởng pod đang chạy nếu dùng `whenUnsatisfiable: ScheduleAnyway` (soft constraint, an toàn hơn hard rule).

---

### 14. Rollout evidence cho Security/Performance changes

**Trụ:** Auditability / Security / Performance  
**Priority:** P2

**Evidence thật**

- Helm release đã qua nhiều revision.
- `checkout` có nhiều ReplicaSet cũ.
- Các thay đổi như NetworkPolicy, quota, HPA, securityContext đều có thể làm gãy app nếu thiếu smoke test.

**Ảnh hưởng khách hàng**

Gián tiếp — không tự nó gây rủi ro, nhưng nếu THIẾU quy trình này, mọi thay đổi Security/Performance khác (NetworkPolicy, quota, HPA, securityContext) có nguy cơ gây lỗi mà team không có cách nhanh nhất để phát hiện/revert, kéo dài downtime nếu 1 thay đổi làm hỏng hệ thống.

**Risk**

Security/Performance changes thường không tạo feature mới nhưng có blast radius lớn. Nếu apply policy/quota/HPA sai, hệ thống có thể lỗi mà team không có bằng chứng rollback rõ.

**Business impact**

- Tăng auditability cho Phase 3.
- Giảm MTTR nếu thay đổi hạ tầng gây lỗi.
- Giúp pitch có bằng chứng trưởng thành vận hành.

**Chi phí/khả thi**

Không tốn chi phí AWS/hạ tầng — là quy trình làm việc (process), tốn thêm ước 15-30 phút/thay đổi để ghi chép before/after evidence.

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

**Rollback / nếu làm sai**

Đây chính là mục ĐỊNH NGHĨA cách rollback cho các mục khác — bản thân nó không có "rollback" riêng, chỉ có thể ngừng áp dụng quy trình (không khuyến khích, vì mất khả năng truy vết mọi thay đổi sau đó).

---

### 15. Chuẩn hóa private access UX cho internal tools

**Trụ:** Security / Auditability / Operations
**Priority:** P2

**Evidence thật**

Mandate #1 hiện đã khóa Grafana, Jaeger và ArgoCD khỏi internet public. Cách truy cập tạm thời là IAM role + SSM bastion + Kubernetes port-forward theo `docs/runbooks/private-access-to-ops-uis.md`.

Luồng này an toàn ở mức least-exposure nhưng khó vận hành khi mở rộng cho nhiều người/team:

```text
nhận bootstrap credential -> assume role -> mở SSM tunnel -> sửa kubeconfig localhost
-> chạy từng port-forward -> nhớ nhiều localhost port -> offboard/thu hồi thủ công
```

Mentor feedback: SSM là tactical fallback tốt để khóa gấp bề mặt tấn công, nhưng UX vận hành "củ chuối" nếu dùng lâu dài. Team cần đưa vào backlog tìm solution private access tốt hơn, ví dụ OpenVPN, Tailscale, NetBird hoặc Cloudflare Zero Trust.

**Ảnh hưởng khách hàng**

Không tác động trực tiếp storefront. Ảnh hưởng gián tiếp tới MTTR và auditability: khi sự cố xảy ra, người có quyền cần vào Grafana/Jaeger/ArgoCD nhanh, đúng quyền, có log truy cập, không phải copy nhiều lệnh thủ công.

**Risk**

- Onboarding/offboarding thủ công dễ cấp dư quyền hoặc quên thu hồi.
- Nhiều bước port-forward làm mentor/operator dễ thao tác sai, nhất là khi cần xử lý sự cố nhanh.
- Dùng localhost port rời rạc khó chuẩn hóa hướng dẫn, khó audit "ai vào tool nào lúc nào".
- Nếu cố đơn giản hóa bằng cách public lại ALB/Ingress cho ops UI thì vi phạm Mandate #1.

**Business impact**

- Giữ nguyên security posture: internal tools không public internet.
- Giảm thời gian cấp quyền cho mentor/team khác.
- Tăng khả năng audit truy cập vận hành.
- Cải thiện trải nghiệm vận hành mà không đánh đổi bằng public exposure.

**Chi phí/khả thi**

Cần spike so sánh chi phí/độ phức tạp:

- **Cloudflare Zero Trust:** UX tốt, access policy theo identity, domain dễ nhớ; cần kiểm tra free/paid limit, connector/tunnel placement và audit log.
- **Tailscale / NetBird:** mesh VPN nhanh, ACL tốt, private DNS/MagicDNS; cần quản lý identity/team và thiết bị.
- **OpenVPN:** quen thuộc, tự chủ cao; ops overhead lớn hơn, phải tự quản server/cert/user.
- **Giữ SSM nhưng wrap script:** rẻ nhất, cải thiện nhanh nhưng vẫn không giải quyết triệt để private domain/audit UX.

**Đề xuất làm**

1. Viết decision spike ngắn so sánh 3-4 option theo: security, audit, onboarding/offboarding, private DNS/domain, cost, effort, rollback.
2. Chọn một target architecture cho internal tools:
   - domain nội bộ dễ nhớ như `grafana.<private-zone>`, `jaeger.<private-zone>`, `argocd.<private-zone>`;
   - chỉ truy cập qua VPN/Zero Trust/tunnel được kiểm soát;
   - không tạo public LoadBalancer/Ingress cho ops UI.
3. Chuẩn hóa onboarding:
   - ai được request quyền;
   - ai approve;
   - quyền theo nhóm/role;
   - thời hạn quyền;
   - cách offboard và audit.
4. Giữ runbook SSM hiện tại làm break-glass/private fallback cho tới khi solution mới được verify.

**Acceptance criteria**

- Có ADR hoặc runbook lựa chọn solution private access dài hạn.
- Người được cấp quyền vào được Grafana/Jaeger/ArgoCD bằng domain dễ nhớ qua đường private.
- Người ngoài internet không resolve/truy cập được các internal tools.
- Có checklist onboarding/offboarding và log/audit truy cập.
- Không dùng lại public ALB/CloudFront path cho Grafana/Jaeger/ArgoCD.

**Rollback / nếu làm sai**

Không gỡ ngay SSM bastion hiện tại. Nếu VPN/Zero Trust/private domain lỗi, disable connector/access policy mới và quay về runbook SSM + port-forward. Storefront không bị ảnh hưởng vì các thay đổi chỉ nằm ở đường truy cập ops UI riêng tư.

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
15. **P2-15 Private access UX:** spike VPN/Zero Trust/private domain thay cho SSM-only vận hành dài hạn.

---

## 6. Việc cố ý chưa ưu tiên trong pitch này

| Việc | Vì sao chưa làm trước |
|---|---|
| Karpenter | Tốt nhưng quá sớm khi chưa có Metrics API, requests, HPA, PDB và cost baseline |
| Managed RDS/ElastiCache/MSK | Quan trọng nhưng là quyết định Reliability/Cost/ADR lớn, dễ vượt budget nếu không có mandate |
| WAF đầy đủ | Có giá trị security nhưng cần cost estimate; trước mắt chốt public boundary và giảm bypass path trước |
| Enforce NetworkPolicy deny-all toàn bộ ngay | Đúng hướng nhưng phải có allowlist và smoke test, nếu không tự làm gãy app |
| Enforce Pod Security `restricted` ngay | Có thể làm gãy workload legacy/polyglot; nên bắt đầu bằng `audit/warn` |
| Thay SSM bastion ngay lập tức | SSM hiện vẫn là break-glass/private fallback an toàn; cần spike VPN/Zero Trust/private domain trước khi cắt sang solution vận hành dài hạn |
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
