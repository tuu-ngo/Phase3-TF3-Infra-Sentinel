# Backlog Week 1 - Performance Efficiency + Security

**Ngày lập:** 09/07/2026  
**Phạm vi:** chỉ gồm 2 trụ Performance Efficiency và Security của team phụ trách.  
**File cũ để tham khảo:** `docs/week1-priority-backlog.md`  
**Nguồn evidence:** live Kubernetes/EKS, Terraform `infra/`, Helm chart `phase3 - information/techx-corp-chart/`, GitHub Actions.

Backlog này không phải danh sách incident đã chắc chắn xảy ra. Cách đọc đúng:

```text
evidence hệ thống đang chạy -> risk có thể ảnh hưởng performance/security -> việc cần làm -> acceptance criteria
```

## 1. Evidence hiện tại

### 1.1 Hệ thống đang chạy

- Cluster: `techx-corp-tf3`
- Region: `ap-southeast-1`
- Namespace app: `techx-tf3`
- Các deployment app hiện đều `1/1`.
- Tất cả service trong namespace app là `ClusterIP`, chưa có `Ingress` hoặc `LoadBalancer`.
- EKS managed add-ons list hiện đang rỗng: `aws eks list-addons` trả `[]`.
- Trong `kube-system` chỉ thấy `coredns`, `aws-node`, `kube-proxy`; chưa thấy `metrics-server`, `cluster-autoscaler`, `karpenter`, `aws-load-balancer-controller`.

### 1.2 Performance evidence

```text
kubectl top nodes
-> error: Metrics API not available

kubectl -n techx-tf3 top pods
-> error: Metrics API not available
```

Resource/QoS live:

```text
Đa số pod: Burstable
llm: BestEffort
grafana: Burstable, restarts 23
jaeger: Burstable, restarts 7
product-catalog: Burstable, restarts 3
```

CPU requests/limits:

- Phần lớn app container không có CPU request/limit.
- Chỉ thấy CPU request/limit rõ ở các sidecar Grafana và `opensearch`.
- Nhiều service critical có memory rất thấp: `checkout` 20Mi, `product-catalog` 20Mi, `currency` 20Mi, `shipping` 20Mi, `valkey-cart` 20Mi, `postgresql` 100Mi.
- `load-generator` có memory 1500Mi, lớn nhất trong app workload nhưng không phục vụ user thật.

Autoscaling:

- Không có HPA.
- Không có `metrics-server`, nên HPA theo CPU/memory chưa có nền tảng.
- Terraform có IRSA role cho `cluster-autoscaler`, nhưng controller chưa được cài.
- Node group hiện `min=3`, `desired=3`, `max=6`; nếu giữ `min=3`, Cluster Autoscaler không thể giảm dưới 3 node.

### 1.3 Security evidence

Đã có:

- EKS API private-only trong `infra/eks.tf`:

```hcl
cluster_endpoint_public_access  = false
cluster_endpoint_private_access = true
```

- Có SSM bastion private-only trong `infra/bastion.tf`:
  - không public IP,
  - không inbound security group rule,
  - dùng IAM + SSM Session Manager,
  - IMDSv2 required.
- EKS secrets được envelope encryption bằng KMS có key rotation.
- CI có gitleaks secret scan trên push/PR vào `main`.
- GitHub Actions build/push dùng OIDC role, không dùng long-lived AWS key trong workflow.

Còn thiếu:

- Không có NetworkPolicy trong `techx-tf3`.
- Không thấy Pod Security Admission label/policy riêng cho namespace.
- Default chart security context đang rỗng; chỉ một số component có `runAsNonRoot`.
- Chưa có ResourceQuota/LimitRange áp dụng.
- Chưa có AWS Load Balancer Controller nếu sau này cần expose bằng ALB.
- Chưa có deploy/GitOps guardrail; deploy Helm hiện vẫn dễ quên `values-flagd-sync.yaml` nếu làm tay.

## 2. P0 - Cần làm trước để có nền đo performance và chặn risk security lớn

### P0-01 - Sửa metrics pipeline để `kubectl top` dùng được

**Trụ:** Performance Efficiency

**Evidence**

```text
kubectl top nodes -> Metrics API not available
kubectl -n techx-tf3 top pods -> Metrics API not available
```

Trong `kube-system` không thấy `metrics-server`.

**Risk**

Không có metrics live thì team không thể:

- right-size CPU/memory có căn cứ,
- thiết kế HPA,
- chứng minh performance efficiency,
- phân biệt thiếu tài nguyên thật với cấu hình sai.

**Việc cần làm**

- Cài hoặc sửa `metrics-server` cho EKS.
- Kiểm tra `APIService` metrics nếu có nhưng không healthy.
- Sau khi chạy được, export bảng usage/request/limit cho các service critical.

**Acceptance criteria**

- `kubectl top nodes` trả CPU/memory.
- `kubectl -n techx-tf3 top pods` trả CPU/memory.
- Có bảng baseline usage cho ít nhất: `frontend-proxy`, `frontend`, `checkout`, `payment`, `cart`, `product-catalog`, `product-reviews`, `postgresql`, `valkey-cart`, `kafka`, `grafana`, `jaeger`.

### P0-02 - Đặt CPU requests cho critical workloads trước khi nói HPA/autoscaling

**Trụ:** Performance Efficiency

**Evidence**

Phần lớn app container không có CPU requests/limits. Pod QoS chủ yếu là `Burstable`, `llm` là `BestEffort`.

**Risk**

- Scheduler không có tín hiệu CPU đúng để đặt pod.
- HPA theo CPU không có nền tảng tin cậy.
- Cluster Autoscaler khó tính đúng capacity cần thêm.
- Noisy neighbor: một service có thể ăn CPU ảnh hưởng service cùng node.

**Việc cần làm**

- Đặt CPU requests trước cho critical path:
  - `frontend-proxy`
  - `frontend`
  - `checkout`
  - `payment`
  - `cart`
  - `product-catalog`
  - `product-reviews`
  - `currency`
  - `shipping`
- Đặt CPU limits cẩn thận sau khi có metrics; không đặt bừa để tránh CPU throttling.
- Ghi rõ giá trị ban đầu là baseline tạm thời, sẽ điều chỉnh sau load test.

**Acceptance criteria**

- `kubectl -n techx-tf3 get pods -o json` cho thấy critical containers có `resources.requests.cpu`.
- Không còn critical service nào hoàn toàn thiếu CPU request.
- Có note về cách chọn số và kế hoạch tune lại sau load test.

### P0-03 - Baseline load test và RED metrics cho browse/cart/checkout path

**Trụ:** Performance Efficiency

**Evidence**

Hiện chỉ mới có GET smoke test nhẹ. Chưa có evidence checkout POST end-to-end, chưa có baseline p95/throughput/error rate theo SLO.

**Risk**

Team có thể nói hệ thống "đang chạy", nhưng không chứng minh được performance theo SLO:

- checkout success >= 99.0%,
- browse/search non-5xx >= 99.5%,
- cart success >= 99.5%,
- frontend p95 latency < 1s.

**Việc cần làm**

- Dùng load-generator/Locust hoặc script riêng để tạo traffic có kiểm soát.
- Đo RED:
  - Rate: request/s theo service/path.
  - Errors: 5xx/error ratio.
  - Duration: p95 latency.
- Chạy riêng 3 nhóm path:
  - browse/product detail/review,
  - cart,
  - checkout test có kiểm soát.

**Acceptance criteria**

- Có bảng baseline p50/p95/error rate cho từng nhóm path.
- Có link/screenshot Grafana/Prometheus/Jaeger hoặc query output.
- Nếu checkout POST không được phép test thật, phải ghi rõ limitation và thay bằng dry-run/safe test path.

## 3. P1 - Tăng năng lực autoscaling và performance tuning

### P1-01 - Cài Cluster Autoscaler đúng IRSA đã có sẵn

**Trụ:** Performance Efficiency

**Evidence**

Terraform đã tạo `cluster_autoscaler_role_arn`, nhưng trong `kube-system` không có deployment `cluster-autoscaler`.

Node group:

```text
min=3, desired=3, max=6
capacity=ON_DEMAND
```

**Risk**

- Khi tăng replicas/HPA, pod có thể Pending nếu node không đủ capacity.
- Team tưởng đã có autoscaling vì infra có IAM role, nhưng thực tế controller chưa chạy.
- Nếu giữ `min=3`, autoscaler không tiết kiệm được dưới 3 node; chỉ giúp scale-up và scale-down về 3.

**Việc cần làm**

- Cài Cluster Autoscaler bằng Helm, dùng service account `kube-system:cluster-autoscaler` và IRSA role đã output.
- Gắn tag/autodiscovery đúng cho managed node group nếu cần.
- Kiểm tra log autoscaler.
- Sau khi Reliability team có replicas/PDB/probes ổn định, mới xem xét giảm `node_min_size`.

**Acceptance criteria**

- `kubectl -n kube-system get deploy cluster-autoscaler` tồn tại.
- Log không có lỗi IAM/OIDC.
- Autoscaler nhìn thấy node group `min=3 max=6`.
- Có note rõ: scale-down cost saving thật sự phụ thuộc vào việc giảm `node_min_size`, không chỉ cài controller.

### P1-02 - Thiết kế HPA cho stateless critical services sau khi có metrics/requests

**Trụ:** Performance Efficiency

**Evidence**

Không có HPA trong namespace. Các deployment hiện `1/1`.

**Risk**

Khi traffic tăng, app không tự scale theo tải. Ngược lại, nếu tạo HPA sớm khi chưa có CPU requests/metrics thì HPA sẽ sai hoặc không hoạt động.

**Việc cần làm**

- Chỉ tạo HPA sau P0-01 và P0-02.
- Ưu tiên stateless services:
  - `frontend-proxy`
  - `frontend`
  - `checkout`
  - `payment`
  - `product-catalog`
  - `cart`
- Chưa HPA datastore: `postgresql`, `valkey-cart`, `kafka`.
- Chọn minReplicas phối hợp với Reliability team để tránh trùng/lệch với PDB.

**Acceptance criteria**

- `kubectl -n techx-tf3 get hpa` hiện HPA cho service đã chọn.
- HPA có target hợp lý, không đặt theo cảm tính.
- Có load test nhẹ chứng minh HPA đọc được metrics.

### P1-03 - Right-size memory cho workload lệch bất thường

**Trụ:** Performance Efficiency

**Evidence**

- `checkout`, `product-catalog`, `currency`, `shipping`, `valkey-cart`: 20Mi.
- `postgresql`: 100Mi.
- `load-generator`: 1500Mi.
- `grafana`: restart 23; `jaeger`: restart 7.

**Risk**

- Memory quá thấp gây OOM/restart, làm sai kết quả performance test.
- Memory quá cao ở load-generator tạo node pressure và làm capacity estimate bị méo.

**Việc cần làm**

- Sau khi có metrics, lập bảng request/limit/usage/restart.
- Điều chỉnh trước các service critical và workload lệch nhất:
  - tăng nếu OOM/rủi ro OOM: `product-catalog`, `checkout`, `postgresql`, `valkey-cart`;
  - giảm/test lại nếu đang cấp quá cao: `load-generator`.
- Tách việc ổn định Grafana/Jaeger với Observability owner, nhưng Performance team cần dùng kết quả đó vì dùng để đo SLO.

**Acceptance criteria**

- Có before/after resource table.
- Không có OOMKilled mới trong window quan sát đã thống nhất.
- Load test baseline không bị sai vì load-generator/observability bị restart.

## 4. P0/P1 Security - Chặn đường vào và giảm blast radius

### S0-01 - Khóa chặt public exposure: giữ ClusterIP, không expose observability UI public

**Trụ:** Security

**Evidence**

Tất cả service app hiện là `ClusterIP`; không có `Ingress`/`LoadBalancer`.

**Risk**

Khi cần demo hoặc truy cập nhanh, team có thể mở ALB/LoadBalancer với scope rộng, làm lộ storefront/admin/observability UI.

**Việc cần làm**

- Ghi decision: hiện tại không public expose bằng Ingress/LB.
- Nếu cần expose, chỉ expose `frontend-proxy`; không expose trực tiếp `grafana`, `jaeger`, `prometheus`, `opensearch`.
- Nếu dùng ALB sau này:
  - cài AWS Load Balancer Controller bằng IRSA đã có,
  - thiết kế TLS/CIDR/auth/WAF nếu cần,
  - có rollback xóa Ingress/LB.

**Acceptance criteria**

- `kubectl -n techx-tf3 get ingress` rỗng cho tới khi có decision.
- `kubectl -n techx-tf3 get svc` không có service `LoadBalancer` ngoài kế hoạch.
- Có security review trước mọi thay đổi public exposure.

### S0-02 - Kiểm soát cluster-admin và SSM bastion access

**Trụ:** Security

**Evidence**

EKS API đã private-only, truy cập qua SSM bastion. Bastion không public IP, không inbound SG rule, IMDSv2 required.

**Risk**

Risk chính không còn là public CIDR nữa, mà là IAM principal nào có quyền:

- start SSM session vào bastion,
- assume/admin vào EKS,
- apply Terraform thay đổi access.

**Việc cần làm**

- Review `eks_admin_principal_arns` trong `infra/terraform.tfvars` local và AWS access entries.
- Review IAM principal nào có quyền SSM Session Manager vào bastion.
- Ghi owner và ngày review cho từng admin.
- Không commit kubeconfig, AWS creds, token, tfvars thật.

**Acceptance criteria**

- Có danh sách admin principal hợp lệ và owner.
- Không có public EKS endpoint.
- Bastion SG không có inbound rule.
- Có runbook revoke access khi thành viên rời team hoặc mất credential.

### S0-03 - Secret hygiene và flagd safety gate

**Trụ:** Security

**Evidence**

Đã có `.github/workflows/secret-scan.yml` dùng gitleaks trên push/PR vào `main`. Phase 3 cấm commit secret thật và cấm đổi/bỏ `flagd` sync.

**Risk**

- Commit nhầm AWS creds/flagd sync token/LLM key làm mất điểm hoặc lộ secret.
- Deploy/Helm upgrade thiếu `values-flagd-sync.yaml` làm mất cơ chế BTC inject incident.

**Việc cần làm**

- Đảm bảo tất cả thành viên đã chạy `scripts/setup-hooks.sh`.
- Thêm checklist deploy: Helm command bắt buộc include `values-flagd-sync.yaml`.
- Thêm PR checklist: không sửa token/URI flagd sync sang nguồn khác, không bypass `flagd`.
- Nếu có deploy workflow sau này, thêm gate verify flagd pod/config còn đúng.

**Acceptance criteria**

- Gitleaks CI pass trên PR.
- Pre-commit hook được setup trên máy người deploy.
- Deploy runbook có mục flagd safety.
- Không có secret thật trong tracked files.

### S1-01 - NetworkPolicy sau khi map service flow

**Trụ:** Security

**Evidence**

Không có NetworkPolicy trong `techx-tf3`.

**Risk**

Nếu một pod bị compromise, nó có thể lateral movement trong namespace tới service không cần thiết: database, observability, Kafka, Valkey, LLM.

**Việc cần làm**

- Map flow trước khi enforce:
  - `frontend-proxy` -> `frontend`
  - `frontend` -> product/cart/checkout/review/recommendation/ad/image/quote
  - `checkout` -> cart/catalog/currency/shipping/payment/email/kafka
  - `product-catalog`, `product-reviews`, `accounting` -> postgresql
  - `cart` -> valkey-cart
  - telemetry -> otel/prometheus/jaeger/opensearch
- Áp NetworkPolicy theo từng bước:
  1. default deny ingress cho namespace test/staging nếu có,
  2. allow frontend path,
  3. allow checkout path,
  4. allow telemetry path,
  5. verify route 200 và trace/log.

**Acceptance criteria**

- Có service flow diagram hoặc bảng allowlist.
- NetworkPolicy không làm hỏng các route smoke test.
- Có rollback command.

### S1-02 - Pod Security baseline cho chart

**Trụ:** Security

**Evidence**

`values.yaml` default:

```yaml
securityContext: {}
```

Chỉ một số component có `runAsNonRoot: true`; chưa thấy baseline đồng nhất cho:

- `allowPrivilegeEscalation: false`
- drop Linux capabilities
- `readOnlyRootFilesystem` nếu service chịu được
- pod-level `runAsNonRoot`
- `seccompProfile`

**Risk**

Nếu container bị khai thác, quyền trong container có thể rộng hơn cần thiết. Đây là risk Security/Auditability, không cần đổi public exposure mới quan trọng.

**Việc cần làm**

- Đặt default security context an toàn cho stateless app trước.
- Kiểm tra service nào cần write filesystem thì exclude có chủ đích.
- Không làm một lần cho toàn bộ stateful/observability nếu chưa test, vì dễ gây crash.

**Acceptance criteria**

- Critical stateless services có `runAsNonRoot: true` và `allowPrivilegeEscalation: false` nếu image hỗ trợ.
- Có danh sách exception có lý do.
- Smoke test route vẫn pass sau thay đổi.

### S1-03 - ResourceQuota/LimitRange như security/cost guardrail

**Trụ:** Security

**Evidence**

Không có `ResourceQuota`/`LimitRange` trong namespace. Có file mẫu `phase3 - information/deploy/quota.yaml`, nhưng chưa apply.

**Risk**

Một deploy xấu hoặc load-generator cấu hình sai có thể chiếm quá nhiều resource, gây denial-of-service nội bộ trong namespace.

**Việc cần làm**

- Chỉ apply sau khi P0-02 có requests cơ bản.
- Điều chỉnh quota vì hiện memory requests/limits và số pod có thể sát ngưỡng mẫu.
- Thêm `LimitRange` để pod mới không chạy kiểu BestEffort như `llm`.

**Acceptance criteria**

- `kubectl -n techx-tf3 get resourcequota,limitrange` có resource.
- Pod mới không thể tạo mà thiếu requests/limits hoàn toàn.
- Quota không chặn việc scale critical services đã được chấp thuận.

## 5. Việc không đưa vào backlog chính của 2 trụ này

| Việc | Lý do |
|---|---|
| Tăng replicas/PDB cho critical path | Chính là Reliability backlog, Performance chỉ phối hợp vì ảnh hưởng HPA/capacity |
| Sửa fake health check/readiness/liveness | Chính là Reliability backlog, Performance chỉ cần biết để load test không sai |
| Migrate Postgres/Valkey/Kafka sang managed service | Reliability/Cost/ADR lớn, không phải Week 1 Performance/Security core |
| Fix checkout rollback/refund | Reliability/Data integrity, không thuộc Performance/Security |
| Expose ALB ngay | Chưa có nhu cầu bắt buộc; nếu làm thì phải qua Security review |
| Cài Karpenter ngay | Quá lớn cho Week 1; hiện IRSA cho Cluster Autoscaler đã có, nên hoàn thiện CA trước |

## 6. Thứ tự thực thi để team review

1. **P0-01** - Sửa metrics-server/metrics API.
2. **P0-02** - Đặt CPU requests cho critical services.
3. **P0-03** - Chạy baseline load test và RED/SLO metrics.
4. **S0-01** - Đóng băng public exposure policy: không expose observability UI public.
5. **S0-02** - Review cluster-admin/SSM bastion access.
6. **S0-03** - Secret hygiene + flagd safety gate.
7. **P1-01** - Cài Cluster Autoscaler bằng IRSA đã có.
8. **P1-02** - Thiết kế HPA sau khi có metrics/requests.
9. **S1-01** - NetworkPolicy sau khi map service flow.
10. **S1-02/S1-03** - Pod Security baseline và quota/limitrange.

## 7. Narrative để pitch ngắn gọn

Team Performance Efficiency + Security không cần nói hệ thống đang chết. Hệ thống đang chạy, nhưng chưa đủ nền vận hành production:

- Performance chưa đo được bằng `kubectl top`, thiếu CPU requests, chưa có HPA/autoscaler controller, chưa có baseline RED/SLO.
- Security đã có nền tốt ở tầng AWS/EKS: private-only API, SSM bastion, KMS encryption, gitleaks/OIDC. Gap còn lại nằm ở Kubernetes runtime: chưa có NetworkPolicy, Pod Security baseline, ResourceQuota/LimitRange, và chưa có guardrail nếu sau này expose public.

Thứ tự đúng là đo được trước, đặt request trước, load test trước; đồng thời khóa chặt access/public exposure trước khi mở thêm ALB/HPA/autoscaler.
