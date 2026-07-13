# Runbook — Truy cập riêng tư các cổng vận hành (Grafana / Jaeger / ArgoCD)

**Cho:** thành viên TF3 + mentor/BTC chấm Mandate #1.
**Nguyên tắc:** storefront **public** qua internet; mọi cổng vận hành **chỉ vào được qua đường riêng**
(SSM bastion → tunnel → `kubectl port-forward`). Internet công khai KHÔNG vào được các cổng này.

> Yêu cầu quyền: IAM identity có `ssm:StartSession` trên bastion + EKS access entry (đọc). Mentor được
> cấp identity/role tạm để tự verify khi chấm.

---

## Điều kiện tiên quyết (một lần)
- `aws` CLI đã đăng nhập account TF3, `kubectl`, quyền SSM tới bastion.
- (Sau khi account AWS được mở lại + bastion dựng lại — xem `docs/runbooks/eks-recovery-after-account-unblock.md`.)

## Bước 1 — Mở SSM tunnel vào EKS API (đường riêng duy nhất)
```bash
# Lấy lệnh đã điền sẵn bastion id:
cd infra && terraform output ssm_tunnel_command
# Chạy lệnh đó (giữ terminal). Dạng:
aws ssm start-session --target <bastion_id> \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters host="<cluster_endpoint>",portNumber="443",localPortNumber="8443" \
  --region ap-southeast-1
```
Terminal khác — trỏ kubectl vào tunnel:
```bash
aws eks update-kubeconfig --name techx-corp-tf3 --region ap-southeast-1
kubectl config set-cluster arn:aws:eks:ap-southeast-1:012619468490:cluster/techx-corp-tf3 \
  --server=https://localhost:8443 --insecure-skip-tls-verify=true
kubectl get nodes    # 3 node Ready
```

## Bước 2 — port-forward tới từng cổng vận hành (ClusterIP, không public)
```bash
# Grafana
kubectl -n techx-tf3 port-forward svc/grafana 3000:80
#   -> mở http://localhost:3000/

# Jaeger
kubectl -n techx-tf3 port-forward svc/jaeger 16686:16686
#   -> mở http://localhost:16686/

# ArgoCD
kubectl -n argocd port-forward svc/argocd-server 8080:443
#   -> mở https://localhost:8080/  (user: admin; lấy pass:)
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d; echo
```
Mỗi lệnh giữ 1 terminal; `Ctrl+C` để đóng khi xong.

## Bước 3 — Xác nhận storefront vẫn PUBLIC, cổng ops KHÔNG public
```bash
# Storefront public -> 200
curl -s -o /dev/null -w "storefront: HTTP %{http_code}\n" https://<storefront-public-url>/

# Ops qua đường public -> KHÔNG vào được (404/403), chỉ vào được qua port-forward ở Bước 2
curl -s -o /dev/null -w "grafana public: HTTP %{http_code}\n" https://<storefront-public-url>/grafana
```
Kỳ vọng: storefront **200**; `/grafana`, `/jaeger`, `/feature` qua public → **404/403**.

## Ghi vết truy cập (Auditability — Mandate #1)
Mọi phiên SSM vào bastion được ghi vào **CloudWatch Logs** (`infra/ssm-session-logging.tf`):
```bash
aws logs tail /techx-corp-tf3/ssm-session-logs --region ap-southeast-1 --since 1h
```
→ thấy IAM identity + thời điểm + lệnh mỗi phiên = bằng chứng "ai truy cập cổng ops, khi nào".

## Lưu ý bảo mật
- **KHÔNG** patch Service Grafana/Jaeger/ArgoCD sang `LoadBalancer`, và **KHÔNG** thêm lại route ops
  vào Envoy public — đó là phơi bày lại đúng cái mandate cấm.
- Grafana đang anonymous-admin: đây là 1 lý do nữa để nó chỉ tồn tại sau đường riêng.
- **flagd**: `/flagservice` (đường service đọc flag) vẫn hoạt động bình thường qua Envoy — KHÔNG phải
  cổng vận hành, KHÔNG gỡ (gỡ = disqualify). Chỉ `/feature` (flagd-ui) mới bị đưa về riêng tư.
