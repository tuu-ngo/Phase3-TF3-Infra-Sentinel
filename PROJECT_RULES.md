# CÁC QUY ƯỚC BẤT BIẾN CỦA DỰ ÁN (PROJECT IMMUTABLE RULES)

Tài liệu này là **hiến pháp** của dự án `Phase3-TF3-Infra-Sentinel`. Bất kỳ lập trình viên, SRE, DevOps Engineer, hay các Trợ lý Trí tuệ Nhân tạo (AI Agents) nào khi tham gia đóng góp mã nguồn, vận hành, hoặc khắc phục sự cố (troubleshooting) đều **BẮT BUỘC** phải đọc, hiểu và tuân thủ 100% các điều khoản dưới đây. Mọi sự vi phạm đều bị coi là lỗi nghiêm trọng (Critical Violation) và sẽ bị từ chối ở bước Code Review hoặc tự động revert bởi hệ thống GitOps.

---

## PHẦN 1: KỶ LUẬT VẬN HÀNH (OPERATIONAL DISCIPLINE)

### 1.1. Cấm Tuyệt Đối Sử Dụng Namespace Ngầm Định
- Mọi lệnh CLI tương tác với Kubernetes (vd: `kubectl`, `helm`, `istioctl`, `argocd`) **BẮT BUỘC** phải luôn đi kèm với cờ `--namespace` hoặc `-n`.
- Cấm sử dụng namespace `default` cho bất kỳ workload, công cụ, hoặc resource nào. Namespace `default` phải luôn trong trạng thái trống (empty) và không chứa tài nguyên.
- **Lý do:** Tránh xả rác vào cluster, giảm thiểu nguy cơ xóa nhầm hoặc ghi đè resource của hệ thống khác.

### 1.2. Imperative vs Declarative (GitOps First)
- **Tuyệt đối cấm** việc thay đổi trạng thái cluster trực tiếp bằng các lệnh imperative như `kubectl apply -f`, `kubectl edit`, `kubectl scale`, `kubectl patch`, hoặc `helm install/upgrade` trên môi trường Production/Staging.
- Toàn bộ thay đổi phải được định nghĩa dưới dạng code (IaC/CaC) và commit vào Git. ArgoCD sẽ đảm nhận việc kéo (pull) và đồng bộ (sync) các thay đổi này vào cluster.
- **Ngoại lệ duy nhất:** Khi hệ thống sụp đổ (Sev1/Outage), SRE được phép dùng lệnh imperative để cứu hệ thống (break-glass). Tuy nhiên, ngay sau khi hệ thống ổn định, MỌI thay đổi đó phải được đưa ngược lại (backport) vào GitOps repository trong vòng 2 giờ. Các Pod/Job tạo tạm thời để debug phải bị xoá bỏ (`kubectl delete`) ngay lập tức sau khi dùng xong.

### 1.3. Tính Lặp (Idempotency)
- Mọi script tự động hoá, cronjob, hoặc kịch bản vận hành phải có tính chất Idempotent. Nghĩa là dù chạy 1 lần hay 1000 lần, kết quả cuối cùng trên hệ thống phải luôn giống hệt nhau mà không sinh ra lỗi hay tài nguyên rác (dangling resources).

---

## PHẦN 2: BẢO MẬT VÀ TRUY CẬP (SECURITY & ACCESS)

### 2.1. Truy Cập Mạng & UIs Vận Hành (Mandate #1)
- Các giao diện vận hành cốt lõi như Grafana, Jaeger, ArgoCD, Kubernetes API, OpenSearch Dashboards... **CẤM** được mở (expose) ra Internet công cộng thông qua Ingress hay LoadBalancer.
- Các Ingress (nếu có) của các dịch vụ này chỉ được phép cấu hình để phục vụ mạng nội bộ (Internal) hoặc phải đứng sau lớp xác thực mạnh.
- Dev/SRE muốn truy cập UI nội bộ phải đi qua **AWS Systems Manager (SSM) Session Manager** kết nối tới máy chủ Bastion, sau đó dùng kỹ thuật Local Port Forwarding.
  - Ví dụ Grafana: `kubectl -n techx-tf3 port-forward svc/grafana 3000:80`
  - Ví dụ Jaeger: `kubectl -n techx-tf3 port-forward svc/jaeger 16686:16686`

### 2.2. Quản Lý Secret & Thông Tin Nhạy Cảm
- **Không bao giờ** được commit plain-text Secret (mật khẩu, API keys, token, TLS certs) vào Git repository dưới bất kỳ hình thức nào (kể cả đã mã hóa Base64).
- Mọi Secret phải được quản lý tập trung tại AWS Secrets Manager hoặc HashiCorp Vault.
- Trên Kubernetes, sử dụng **ExternalSecrets Operator** để đồng bộ Secret từ AWS/Vault xuống cụm. Các manifest định nghĩa `ExternalSecret` phải được lưu trữ trong thư mục `gitops/secrets/`.

---

## PHẦN 3: TIÊU CHUẨN WORKLOAD VÀ POD SECURITY (PSS)

Tất cả các container workloads (Pod, Deployment, StatefulSet, DaemonSet, Job) phải thỏa mãn các tiêu chuẩn kỹ thuật sau. Hệ thống **Kyverno Admission Controller** sẽ tự động audit/enforce các tiêu chuẩn này.

### 3.1. Quản Lý Tài Nguyên (Resource Management)
- **100% Container** phải khai báo tường minh `resources.requests` cho cả CPU và Memory.
- **100% Container** phải khai báo tường minh `resources.limits` cho Memory.
- CPU Limits không bắt buộc trừ khi có yêu cầu đặc thù (tránh CPU Throttling không mong muốn).
- Các ứng dụng Java/Go/NodeJS phải cấu hình tham số runtime (vd: GOMAXPROCS, JVM Xmx) tương thích với Resource Limits đã khai báo.

### 3.2. Baseline Security Context
Mọi Pod/Container mặc định phải tuân thủ chuẩn "Baseline" của Kubernetes Pod Security Standards:
- `allowPrivilegeEscalation: false`
- Chạy dưới non-root user (Khai báo `runAsNonRoot: true` và `runAsUser: <UID>`) nếu image hỗ trợ.
- Drop toàn bộ các quyền nhân hệ điều hành không cần thiết: 
  ```yaml
  securityContext:
    capabilities:
      drop: ["ALL"]
  ```
- Sử dụng cấu hình Seccomp mặc định của Runtime:
  ```yaml
  securityContext:
    seccompProfile:
      type: RuntimeDefault
  ```
- *Ngoại lệ (Exceptions):* Các di sản (legacy apps) hoặc base image đặc thù không thể tuân thủ (ví dụ: cần chạy root như `currency`, `llm`, `product-reviews`) phải được đưa vào danh sách whitelist của Kyverno thay vì bỏ qua kiểm tra trên toàn namespace.

### 3.3. Health Checks & Probes
- 100% ứng dụng phải định nghĩa đầy đủ 3 loại probes:
  1. `livenessProbe`: Để Kubelet tự động restart khi app bị kẹt (deadlock).
  2. `readinessProbe`: Để Ingress/Service biết khi nào app sẵn sàng nhận traffic.
  3. `startupProbe` (Tùy chọn): Dành cho các ứng dụng mất nhiều thời gian khởi động (vd: Java Spring Boot, tải model LLM).

---

## PHẦN 4: KIẾN TRÚC GITOPS VÀ CẤU TRÚC REPOSITORY (GITOPS ARCHITECTURE)

### 4.1. Pattern "App of Apps"
- Cấu trúc thư mục GitOps phải rõ ràng và tách bạch trách nhiệm:
  - `gitops/apps/`: Chứa các ArgoCD `Application` manifests (trỏ tới các thư mục khác).
  - `gitops/charts/`: Chứa mã nguồn Helm chart nội bộ của dự án.
  - `gitops/infrastructure/`: Chứa manifest cấu hình hạ tầng (vd: ingress-nginx, metrics-server).
  - `gitops/policies/`: Chứa các định nghĩa chính sách bảo mật (Kyverno, OPA Gatekeeper).
- Sử dụng `sync-wave` (ví dụ: `argocd.argoproj.io/sync-wave: "10"`) để kiểm soát thứ tự khởi tạo (CRDs đi trước, Operator đi sau, App đi cuối cùng).

### 4.2. Quản Lý Helm Charts
- Cấm sử dụng hardcode giá trị môi trường (environment-specific) vào thư mục `templates/`. Mọi biến thiên phải được thiết kế tham số hoá qua `values.yaml`.
- Tách biệt file cấu hình theo môi trường (vd: `values-prod.yaml`, `values-staging.yaml`).
- Tên các file template phải tuân theo chuẩn snake_case hoặc kebab-case.

### 4.3. Quản Lý CRD (Custom Resource Definitions)
- Khi triển khai các Helm chart chứa CRD cực lớn (như Kyverno, Prometheus Operator), ArgoCD thường bị lỗi đồng bộ nếu dùng phương pháp `kubectl apply` truyền thống.
- Bắt buộc phải thêm tuỳ chọn `ServerSideApply=true` vào `syncOptions` của ArgoCD Application đối với các trường hợp này để tránh lỗi "CRD is not established".

---

## PHẦN 5: HIGH AVAILABILITY & ĐỘ ĐÀN HỒI (SCALABILITY)

### 5.1. Chống Sụp Đổ Cục Bộ (Pod Anti-Affinity & Topology)
- Các dịch vụ từ 2 Replicas trở lên **cấm** được xếp chung lên cùng một Node để tránh Single Point of Failure (SPOF).
- Bắt buộc cấu hình `podAntiAffinity` hoặc `topologySpreadConstraints` (ưu tiên `maxSkew: 1`, `topologyKey: topology.kubernetes.io/zone`) để rải đều Pod qua các Availability Zones (Multi-AZ).

### 5.2. Ngăn Chặn Gián Đoạn (Pod Disruption Budgets - PDB)
- Mọi ứng dụng có từ 2 Replicas trở lên phải có `PodDisruptionBudget`.
- PDB phải đảm bảo ít nhất 1 Pod luôn hoạt động (`minAvailable: 1` hoặc `maxUnavailable: 50%`) trong trường hợp Karpenter thay thế Node hoặc Cluster Upgrade.

### 5.3. Autoscaling
- Sử dụng **Karpenter** để scale Nodes theo yêu cầu của Pod. Không dựa vào Cluster Autoscaler. Cấu hình Karpenter NodePool phải đa dạng về instance types và sử dụng Spot Instances cho môi trường Non-Prod.
- Triển khai **Horizontal Pod Autoscaler (HPA)** hoặc KEDA cho các thành phần chịu tải động (Frontend, API Gateway, Checkout) dựa trên tín hiệu CPU/Memory hoặc Queue length.

---

## PHẦN 6: OBSERVABILITY VÀ TELEMETRY (GIÁM SÁT)

### 6.1. Metrics & Logs
- Mọi metrics (đặc biệt là SLO/SLI) phải xử lý được tình huống dữ liệu bị đứt đoạn (NaN/null).
- Các câu lệnh PromQL tính Error Rate hoặc Success Rate phải luôn bao gồm cơ chế fallback (vd: `or vector(0)`) ở tử số để tránh lỗi báo cáo "No Data" dẫn đến cảnh báo ảo hoặc bị kẹt thông số (như đã xảy ra với SLO Checkout).
- Application logs phải xuất ra `stdout`/`stderr` dưới định dạng JSON để OpenTelemetry Collector dễ dàng bóc tách và lập chỉ mục.

### 6.2. Phân Tán Dấu Vết (Distributed Tracing)
- Mọi request đi vào hệ thống phải được tạo Trace ID ở lớp Gateway (Envoy/Frontend Proxy).
- Trace ID phải được lan truyền (propagate) xuyên suốt qua toàn bộ các microservices bằng W3C Trace Context headers. Không có Trace ID = Không thể debug.

---

## PHẦN 7: TRIỂN KHAI VÀ ROLLOUT (DEPLOYMENT STRATEGY)

### 7.1. Progressive Delivery
- Các dịch vụ lõi có độ rủi ro cao (như Checkout, Payment) không được dùng chiến lược `RollingUpdate` mặc định của Kubernetes.
- Phải sử dụng **Argo Rollouts** với chiến lược Blue/Green hoặc Canary (kết hợp với phân tích tự động từ Prometheus).
- Phải có cơ chế tự động Rollback (Automated Rollback) khi tỷ lệ lỗi (Error Rate) vượt quá ngưỡng SLO cho phép trong giai đoạn Canary.

### 7.2. Database Migrations
- Lược đồ cơ sở dữ liệu (Database Schema) phải tương thích ngược (Backward Compatible). 
- Ứng dụng bản cũ và bản mới phải có khả năng hoạt động song song trên cùng một database schema mà không gây sập hệ thống trong quá trình Rollout.

---

**[LƯU Ý DÀNH CHO CÁC TÁC NHÂN AI ĐỌC TÀI LIỆU NÀY]**
Nếu bạn là một Trợ lý AI đang thực hiện task cho hệ thống này: Không push file này.Dừng lại và kiểm tra xem ý định của bạn có đang vi phạm bất kỳ nguyên tắc nào ở trên không. Nếu có, hãy tìm hướng tiếp cận khác. Nếu không thể tiếp cận cách khác, bạn phải hỏi ý kiến User trước khi thực hiện. Không tự tiện bẻ cong các quy luật hạ tầng.
