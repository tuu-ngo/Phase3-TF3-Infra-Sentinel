# Supporting 01 — Observability Command Runbook

## 1. Reliability

### 1.1 Session variables

```powershell
$NS='techx-tf3'
$TEST_ID='mandate02-YYYYMMDD-HHMM'
$TEST_START='YYYY-MM-DDTHH:mm:ss+07:00'
$TEST_END='YYYY-MM-DDTHH:mm:ss+07:00'
```

Chạy cùng bộ snapshot tại `before`, `peak`, `after`:

```powershell
Get-Date -Format o
kubectl -n $NS get hpa
kubectl -n $NS get pods -o wide
kubectl -n $NS top pods --containers
kubectl -n $NS get resourcequota
kubectl -n $NS get events --sort-by=.lastTimestamp
kubectl get nodes -o wide
kubectl get nodeclaims -o wide
kubectl top nodes
```

### 1.2 HPA

```powershell
kubectl -n $NS get hpa --watch
```

```powershell
$replicas=kubectl -n $NS get hpa -o jsonpath='{range .items[*]}{.status.currentReplicas}{"\n"}{end}'
($replicas | ForEach-Object {[int]$_} | Measure-Object -Sum).Sum
```

HPA conditions:

```powershell
kubectl -n $NS get hpa -o custom-columns='NAME:.metadata.name,CURRENT:.status.currentReplicas,DESIRED:.status.desiredReplicas,ABLE:.status.conditions[?(@.type=="AbleToScale")].status,ACTIVE:.status.conditions[?(@.type=="ScalingActive")].status,LIMITED:.status.conditions[?(@.type=="ScalingLimited")].status'
```

### 1.3 OOM và restart

```powershell
kubectl -n $NS get pods -o custom-columns='POD:.metadata.name,PHASE:.status.phase,RESTARTS:.status.containerStatuses[*].restartCount,LAST_REASON:.status.containerStatuses[*].lastState.terminated.reason,LAST_EXIT:.status.containerStatuses[*].lastState.terminated.exitCode'
kubectl -n $NS get events --field-selector=reason=OOMKilling --sort-by=.lastTimestamp
```

```promql
increase(kube_pod_container_status_restarts_total{namespace="techx-tf3"}[5m])
```

```promql
max_over_time(kube_pod_container_status_last_terminated_reason{namespace="techx-tf3",reason="OOMKilled"}[5m])
```

### 1.4 Pending và scheduling

```powershell
kubectl -n $NS get pods --field-selector=status.phase=Pending -o wide
kubectl -n $NS get events --sort-by=.lastTimestamp | Select-String -Pattern 'FailedScheduling|Exceeded quota|Insufficient|topology'
```

Khi có Pending:

```powershell
kubectl -n $NS describe pod <POD_NAME>
kubectl -n $NS get events --field-selector=involvedObject.name=<POD_NAME> --sort-by=.lastTimestamp
```

### 1.5 CPU throttling và memory saturation

```promql
sum by (pod) (rate(container_cpu_cfs_throttled_periods_total{namespace="techx-tf3",container!=""}[2m]))
/
sum by (pod) (rate(container_cpu_cfs_periods_total{namespace="techx-tf3",container!=""}[2m]))
```

```promql
sum by (pod,container) (container_memory_working_set_bytes{namespace="techx-tf3",container!=""})
/
sum by (pod,container) (kube_pod_container_resource_limits{namespace="techx-tf3",resource="memory",unit="byte"})
```

### 1.6 5xx và SLO

Metric name/label phải được xác nhận trên Prometheus live trước test.

```promql
sum(rate(http_server_request_duration_seconds_count{namespace="techx-tf3",http_response_status_code=~"5.."}[2m]))
/
sum(rate(http_server_request_duration_seconds_count{namespace="techx-tf3"}[2m]))
```

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_request_duration_seconds_bucket{namespace="techx-tf3",service_name="frontend"}[2m])
  )
)
```

## 2. Cost Optimization

### 2.1 Node inventory

```powershell
kubectl get nodes -o custom-columns='NODE:.metadata.name,INSTANCE:.metadata.labels.node\.kubernetes\.io/instance-type,CAPACITY_TYPE:.metadata.labels.karpenter\.sh/capacity-type,ZONE:.metadata.labels.topology\.kubernetes\.io/zone,CREATED:.metadata.creationTimestamp'
kubectl get nodeclaims -o custom-columns='NAME:.metadata.name,NODE:.status.nodeName,INSTANCE:.status.instanceType,CAPACITY_TYPE:.metadata.labels.karpenter\.sh/capacity-type,CREATED:.metadata.creationTimestamp'
kubectl get nodepool flash-sale-spot -o jsonpath='{.spec.disruption.consolidateAfter}'
```

### 2.2 Cleanup verification

```powershell
kubectl -n $NS get pods -o custom-columns='POD:.metadata.name,DO_NOT_DISRUPT:.metadata.annotations.karpenter\.sh/do-not-disrupt,NODE:.spec.nodeName'
kubectl get nodepool flash-sale-spot -o jsonpath='{.spec.disruption.consolidateAfter}'
kubectl get nodeclaims -o wide
```

Expected after cleanup:

- `consolidateAfter=2m`.
- Pod mới của 7 component không còn `do-not-disrupt`.
- HPA-managed replica = 16.
- Node count không cao hơn before.

