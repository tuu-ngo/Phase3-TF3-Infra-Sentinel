# Runbook — checkout canary bằng Argo Rollouts

## Phạm vi và guardrail

- Controller được quản lý bởi `gitops/apps/argo-rollouts-app.yaml`; không `kubectl apply` controller/CRD bằng tay.
- `checkout` chuyển đổi an toàn qua `workloadRef` từ Deployment hiện hữu sang `checkout-rollout`. Controller scale Deployment cũ xuống dần, không delete/recreate checkout.
- Giữ nguyên `checkout-pdb` (`minAvailable: 1`) và `checkout-hpa` (`minReplicas: 2`, `maxReplicas: 8`). HPA target là `checkout-rollout`.
- Canary native điều phối theo **tỷ lệ pod replica**. Vì checkout là traffic nội bộ gRPC, đây không phải cam kết phần trăm request chính xác; chưa tuyên bố 20% traffic thật nếu chưa có traffic router/service mesh.

## Điều kiện trước khi sync

1. Có SSM tunnel tới EKS và quyền đọc `argocd`, `argo-rollouts`, `techx-tf3`.
2. Prometheus `prometheus.techx-tf3.svc.cluster.local:9090` query được spanmetrics; `rollouts_pod_template_hash` xuất hiện trên `traces_span_metrics_calls_total`.
3. Load-generator chạy checkout-heavy liên tục trong tối thiểu 12 phút. Analysis sẽ abort nếu canary dưới `0.05 req/s`, để không coi lack-of-traffic là pass.
4. Không có deploy checkout khác đang chạy.

## Xác minh controller và migration

```sh
kubectl -n argocd get application argo-rollouts techx-corp techx-infrastructure-app
kubectl -n argo-rollouts rollout status deployment/argo-rollouts
kubectl get crd rollouts.argoproj.io analysistemplates.argoproj.io analysisruns.argoproj.io
kubectl -n techx-tf3 get rollout checkout-rollout
kubectl -n techx-tf3 get hpa checkout-hpa pdb checkout-pdb
```

Trong lúc canary, theo dõi:

```sh
kubectl argo rollouts get rollout checkout-rollout -n techx-tf3 --watch
kubectl -n techx-tf3 get analysisrun -w
kubectl -n techx-tf3 get pods -l opentelemetry.io/name=checkout -w
```

## Analysis và điều kiện abort

`checkout-slo` đo spanmetrics thật từ Prometheus, theo từng revision hash:

- canary request rate phải >= `0.05 req/s`;
- canary success rate >= `99.0%`;
- canary không được thấp hơn stable quá `0.5` điểm phần trăm;
- canary p95 <= `1000ms` và không chậm hơn stable quá `100ms`.

Mỗi metric đợi warm-up ba phút, sau đó lấy ba mẫu cách nhau hai phút; một failure abort rollout. Các query đều hiện trên `AnalysisRun.status.metricResults` để lưu evidence.

## Demo rollback có chủ đích

Chỉ chạy trong test window đã được duyệt và khi load-generator checkout-heavy đang hoạt động. Tạo commit tạm với override dưới đây trong `phase3 - information/deploy/values-prod.yaml`, rồi merge/sync qua ArgoCD:

```yaml
components:
  checkout:
    envOverrides:
      - name: PAYMENT_ADDR
        value: payment.invalid:8080
```

Readiness của checkout vẫn có thể pass, nhưng checkout request sẽ lỗi khi gọi payment. Theo dõi `AnalysisRun`: `checkout-canary-success-rate` hoặc `checkout-success-rate-regression-vs-stable` phải Failed, Rollout chuyển `Degraded`, và canary ReplicaSet scale về 0 trước promotion 100%.

Sau khi capture `AnalysisRun`, Rollout status, query Prometheus và checkout SLO, revert đúng commit tạm qua Git. Không dùng `kubectl promote`, `kubectl abort`, hay sửa env trực tiếp làm steady-state vì ArgoCD self-heal sẽ ghi đè.

## Evidence thực thi ngày 2026-07-14

GitOps target là `deploy/account-migration-gitops`. Controlled-failure được tạo bằng `PAYMENT_ADDR=payment.invalid:8085`; commit khôi phục steady state là `42cd109`.

Do checkout là gRPC nội bộ với connection lâu sống, frontend hiện hữu có thể tiếp tục bám stable endpoint dù canary pod đã được tạo. Để tạo tín hiệu canary xác định mà không đổi selector của production Service, bài test dùng pod `grpcurl` tạm thời gọi trực tiếp `PlaceOrder` vào canary hash `7f898c8f5d`. Pod test và ConfigMap proto đều được xóa sau khi chạy. Request thất bại đúng lỗi đã tiêm:

```text
Code: Internal
Message: failed to charge card: could not charge the card:
rpc error: code = Unavailable desc = name resolver error: produced zero addresses
```

AnalysisRun `checkout-rollout-7f898c8f5d-8-4` lấy dữ liệu thật từ Prometheus và tự fail ở bước 50%, trước promotion 100%:

```text
checkout-request-rate                         Successful  0.8061777777777779
checkout-canary-p95-latency-ms                Successful  4.900000000000001
checkout-p95-regression-vs-stable-ms          Successful -37.09999999999996
checkout-canary-success-rate                  Failed      0.9473179337339435
checkout-success-rate-regression-vs-stable    Failed      0.048870033099454036
```

Controller đặt `abort=true`, scale canary ReplicaSet về `0`, giữ stable ReplicaSet `5d97c8878` ở `2/2`. Sau commit khôi phục, trạng thái cuối:

```text
Rollout checkout-rollout: Healthy, stable=current=5d97c8878, available=2
Deployment checkout: desired=0
HPA checkout-hpa: Rollout/checkout-rollout, min=2, max=8, replicas=2
PDB checkout-pdb: minAvailable=1, allowedDisruptions=1
Stable success rate [2m]: 1.0
Stable p95 [2m]: 31.882435294117663 ms
Argo Rollouts Application: Synced / Healthy, chart revision 2.41.0
```

Trong cùng cửa sổ khôi phục, live cluster được reconcile với cấu hình EBS CSI đã có trong Terraform. Addon `aws-ebs-csi-driver` đạt `ACTIVE`; `valkey-cart` 1Gi và `postgresql-data` 2Gi đều `Bound`, hai datastore pod trở lại `Ready` trước khi chốt evidence SLO.
