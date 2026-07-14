# Báo cáo thực thi Backlog #14 — Checkout Canary với Argo Rollouts

**Ngày thực hiện:** 14/07/2026

**Nhánh triển khai:** `feat/checkout-canary-rollouts`

**Nhánh GitOps đích:** `deploy/account-migration-gitops`

**Phạm vi chính:** `checkout`, Argo Rollouts controller, Prometheus Analysis và bằng chứng rollback tự động

## 1. Kết quả tổng quan

Tôi đã thay cơ chế rollout của `checkout` từ Kubernetes `Deployment` rolling update thông thường sang Argo `Rollout` canary được quản lý bằng ArgoCD. Canary được kiểm tra tự động bằng span metrics thật từ Prometheus, gồm request rate, success rate, p95 latency và độ regression so với stable revision.

Một bản lỗi có chủ đích đã được triển khai với `PAYMENT_ADDR` không hợp lệ. Request checkout thật được gửi trực tiếp vào canary; AnalysisRun phát hiện success rate giảm còn `94.73%`, tự đặt rollout về trạng thái abort và scale canary về `0` trước khi bản lỗi được promote lên 100%.

Sau demo, cấu hình lỗi đã được xóa khỏi Git. Checkout trở lại `Healthy`, stable giữ `2/2` pod, success rate cửa sổ 2 phút đạt `100%` và p95 đạt `31.88ms`.

## 2. Các thay đổi đã thực hiện

### 2.1 Cài Argo Rollouts qua GitOps

Tạo ArgoCD Application riêng tại `gitops/apps/argo-rollouts-app.yaml`:

- Helm chart `argo-rollouts` phiên bản `2.41.0`;
- controller Argo Rollouts `v1.9.0`;
- namespace `argo-rollouts` được ArgoCD tự tạo;
- bật `automated`, `prune` và `selfHeal`;
- dùng sync wave `-2` để CRD có trước khi chart ứng dụng tạo Rollout.

Trạng thái cuối:

```text
NAME            SYNC     HEALTH    REVISION
argo-rollouts   Synced   Healthy   2.41.0

argo-rollouts-85fb94984c-6btdh   1/1   Running
argo-rollouts-85fb94984c-7rj4x   1/1   Running
```

Các CRD đã có trên cluster:

```text
rollouts.argoproj.io
analysistemplates.argoproj.io
analysisruns.argoproj.io
```

### 2.2 Chuyển checkout sang Rollout

Tạo `checkout-rollout` bằng `workloadRef` trỏ tới Deployment hiện hữu:

```yaml
workloadRef:
  apiVersion: apps/v1
  kind: Deployment
  name: checkout
  scaleDown: progressively
```

Chiến lược canary:

```text
20% -> Analysis -> pause 5 phút
50% -> Analysis -> pause 5 phút
100%
```

Guardrail availability:

- `maxSurge: 1`;
- `maxUnavailable: 0`;
- HPA target chuyển sang `Rollout/checkout-rollout`;
- HPA giữ `minReplicas: 2`, `maxReplicas: 8`;
- PDB giữ `minAvailable: 1`.

Trạng thái ownership cuối:

```text
Deployment checkout: desired=0
Rollout checkout-rollout: desired=2, available=2, Healthy
HPA checkout-hpa: Rollout/checkout-rollout, min=2, max=8
PDB checkout-pdb: minAvailable=1
```

### 2.3 AnalysisTemplate dùng Prometheus thật

Tạo `AnalysisTemplate/checkout-slo`, truy vấn trực tiếp:

```text
http://prometheus.techx-tf3.svc.cluster.local:9090
```

Metrics được tách theo `rollouts_pod_template_hash` để so sánh canary với stable:

| Metric | Điều kiện pass |
|---|---:|
| Canary request rate | `>= 0.05 req/s` |
| Canary success rate | `>= 99.0%` |
| Success regression so với stable | `<= 0.5` điểm phần trăm |
| Canary p95 | `<= 1000ms` |
| p95 regression so với stable | `<= 100ms` |

Mỗi metric warm-up 3 phút, sau đó lấy 3 mẫu cách nhau 2 phút. `failureLimit: 0` khiến lần đo xấu đầu tiên abort rollout.

## 3. Các vấn đề đã phát hiện và xử lý

### 3.1 Image checkout nằm ở ECR account khác

Node của cluster ban đầu nhận `403 Forbidden` khi pull image checkout. Tôi đã giới hạn ECR repository policy cho đúng EKS node role và chỉ cấp ba quyền pull cần thiết:

```text
ecr:BatchCheckLayerAvailability
ecr:BatchGetImage
ecr:GetDownloadUrlForLayer
```

Sau khi policy được cập nhật, checkout image pull thành công và pod Rollout lên `Running`.

### 3.2 Prometheus wiring và thời gian warm-up

Trong các lần chạy đầu, AnalysisRun phát hiện ba vấn đề:

1. `canary-hash` và `stable-hash` chưa được truyền từ Rollout;
2. Prometheus dùng short DNS name nên controller ở namespace `argo-rollouts` resolve sai namespace;
3. Analysis đo ngay khi canary vừa tạo nên series chưa có đủ scrape samples.

Các sửa đổi cuối cùng:

- truyền hash bằng `podTemplateHashValue: Latest/Stable`;
- dùng Prometheus service FQDN;
- thêm `initialDelay: 3m`;
- bảo đảm PromQL luôn trả về scalar khi series chưa tồn tại.

### 3.3 gRPC connection bám stable revision

Checkout là gRPC nội bộ. Frontend giữ connection lâu sống nên việc tăng tỷ lệ pod không bảo đảm frontend lập tức gửi request sang canary. Vì vậy, để có test xác định mà không sửa production Service selector, tôi đã:

1. tạo ConfigMap proto tạm từ `demo.proto`;
2. dùng pod `grpcurl` tạm thêm một item vào cart của user demo;
3. gọi trực tiếp `CheckoutService/PlaceOrder` vào IP canary;
4. xóa cart demo, pod test và ConfigMap sau khi capture evidence.

Không còn resource `grpcurl` hoặc `grpcurl-demo-proto` sau test.

### 3.4 Khôi phục persistence cho Valkey và PostgreSQL

Khi GitOps bắt đầu quản lý cấu hình datastore, hai PVC `gp2` bị `Pending` vì live cluster chưa có EBS CSI driver dù Terraform đã khai báo addon và node policy. Valkey và PostgreSQL từng được chuyển tạm sang `emptyDir` để phục hồi dependency trong lúc điều tra.

Sau demo, tôi đã reconcile live cluster với cấu hình đã có trong Terraform:

- gắn `AmazonEBSCSIDriverPolicy` cho EKS node role;
- tạo EKS managed addon `aws-ebs-csi-driver`;
- đưa volume mount của Valkey và PostgreSQL trở lại PVC;
- bật lại `persistence.enabled: true` cho Valkey.

Trạng thái cuối:

```text
aws-ebs-csi-driver   ACTIVE   v1.62.0-eksbuild.1

postgresql-data   Bound   2Gi   gp2
valkey-cart       Bound   1Gi   gp2

postgresql-7646878db4-mrskj   Ready   Running
valkey-cart-576455789-6zk7w   Ready   Running
```

Hai PVC cũ chưa từng bind trước khi EBS CSI được cài, vì vậy không có dữ liệu EBS cũ bị xóa. Dữ liệu phát sinh trong giai đoạn chạy tạm bằng `emptyDir` không được migrate sang volume mới.

## 4. Demo lỗi và rollback tự động

### 4.1 Lỗi được tiêm

Checkout canary revision 8 dùng cấu hình tạm:

```yaml
envOverrides:
  - name: PAYMENT_ADDR
    value: payment.invalid:8085
```

Canary vẫn vượt readiness, nhưng request `PlaceOrder` thật thất bại khi charge payment:

```text
Code: Internal
Message: failed to charge card: could not charge the card:
rpc error: code = Unavailable desc = name resolver error: produced zero addresses
```

### 4.2 Kết quả AnalysisRun

AnalysisRun: `checkout-rollout-7f898c8f5d-8-4`

```text
checkout-request-rate                         Successful   0.8061777777777779
checkout-canary-p95-latency-ms                Successful   4.900000000000001
checkout-p95-regression-vs-stable-ms          Successful  -37.09999999999996
checkout-canary-success-rate                  Failed       0.9473179337339435
checkout-success-rate-regression-vs-stable    Failed       0.048870033099454036
```

Controller phản ứng:

```text
analysis=Failed
Metric "checkout-canary-success-rate" assessed Failed
Rollout abort=true
Canary ReplicaSet desired=0
Stable ReplicaSet 5d97c8878 desired=2, ready=2
```

Rollout bị abort tại Analysis bước 50%, chưa bao giờ promote bản lỗi lên 100%.

## 5. Khôi phục steady state và SLO

Sau khi lấy evidence, tôi xóa toàn bộ `envOverrides` lỗi khỏi Git và để ArgoCD đưa checkout về stable revision.

```text
PAYMENT_ADDR=payment:8080
checkout-rollout: Healthy
stableRS=currentPodHash=5d97c8878
availableReplicas=2
```

Prometheus sau rollback, cùng cửa sổ 2 phút mà AnalysisTemplate sử dụng:

```text
Stable checkout success rate: 1.0 (100%)
Stable checkout p95:          31.882435294117663 ms
Stable error rate:            0
```

Trong lần đo abort, stable success rate suy ra từ canary và regression vẫn khoảng `99.62%`, trên SLO checkout `99%`. Traffic test được gọi trực tiếp vào canary nên không cần đổi production Service selector.

## 6. Checklist Definition of Done

- [x] Argo Rollouts controller Running và được quản lý bởi ArgoCD Application riêng.
- [x] Checkout chạy dưới `Rollout` canary thay cho Deployment rolling update.
- [x] AnalysisTemplate dùng request rate, success rate và p95 thật từ Prometheus.
- [x] Bản lỗi có chủ đích bị AnalysisRun tự động abort trước 100%.
- [x] Canary ReplicaSet được scale về 0, stable vẫn 2/2.
- [x] HPA min replicas và PDB của REL-01 được giữ nguyên.
- [x] Checkout stable giữ SLO và trở lại `Healthy` sau test.
- [x] Cấu hình lỗi và resource test tạm đã được dọn sạch.
- [x] Valkey và PostgreSQL đã trở lại PVC `Bound`.

## 7. Các commit chính

| Commit | Nội dung |
|---|---|
| `edb4686` | Cài controller GitOps, Rollout checkout, AnalysisTemplate và runbook |
| `7d4b911` | Truyền stable/canary pod template hash vào AnalysisRun |
| `60f884c` | Dùng Prometheus service FQDN |
| `8b3bf3e` | Thêm metric warm-up và sửa PromQL empty-series |
| `8e92134` | Tiêm lỗi payment có chủ đích |
| `42cd109` | Xóa lỗi test và khôi phục checkout |
| `cd35829` | Khôi phục PVC mount cho Valkey và PostgreSQL |
| `b96abdd` | Ghi lại evidence rollback trong runbook |

Tất cả commit đã được push lên `feat/checkout-canary-rollouts` và `deploy/account-migration-gitops`.

## 8. Trạng thái ArgoCD cuối cùng

```text
argo-rollouts   Synced      Healthy
techx-corp      OutOfSync   Healthy
```

`techx-corp` còn `OutOfSync` duy nhất ở `Ingress/frontend-proxy`, là drift có trước và nằm ngoài phạm vi checkout canary. Rollout checkout, controller, PVC và các datastore đều Healthy/Ready.

Runbook vận hành và lệnh tái hiện: [`docs/runbooks/checkout-argo-rollouts-canary.md`](../runbooks/checkout-argo-rollouts-canary.md).
