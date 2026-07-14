# Runbook — checkout canary bằng Argo Rollouts

## Phạm vi và guardrail

- Controller được quản lý bởi `gitops/apps/argo-rollouts-app.yaml`; không `kubectl apply` controller/CRD bằng tay.
- `checkout` chuyển đổi an toàn qua `workloadRef` từ Deployment hiện hữu sang `checkout-rollout`. Controller scale Deployment cũ xuống dần, không delete/recreate checkout.
- Giữ nguyên `checkout-pdb` (`minAvailable: 1`) và `checkout-hpa` (`minReplicas: 2`, `maxReplicas: 5`). HPA target là `checkout-rollout`.
- Canary native điều phối theo **tỷ lệ pod replica**. Vì checkout là traffic nội bộ gRPC, đây không phải cam kết phần trăm request chính xác; chưa tuyên bố 20% traffic thật nếu chưa có traffic router/service mesh.

## Điều kiện trước khi sync

1. Có SSM tunnel tới EKS và quyền đọc `argocd`, `argo-rollouts`, `techx-tf3`.
2. Prometheus `prometheus-server` query được spanmetrics; `rollouts_pod_template_hash` xuất hiện trên `traces_span_metrics_calls_total` sau collector restart.
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

Mỗi metric lấy ba mẫu, cách nhau hai phút; một failure abort rollout. Các query đều hiện trên `AnalysisRun.status.metricResults` để lưu evidence.

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
