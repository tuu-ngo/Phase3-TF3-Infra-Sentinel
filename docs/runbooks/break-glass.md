# Runbook: Break-Glass — Kubectl apply khẩn cấp ngoài GitOps

> **Chỉ dùng khi:** ArgoCD không hoạt động, cluster đang sập, không thể mở PR trong thời gian
> cần thiết để ngăn mất dữ liệu hoặc downtime kéo dài.
>
> **Không dùng cho:** convenience, "nhanh hơn PR", test thử.
>
> **Sau khi dùng:** BẮT BUỘC mở PR để đưa thay đổi vào Git trong vòng 24h.

---

## Tại sao có runbook này

Kyverno policy `audit-sensitive-resource-changes` (mode: **Enforce**) sẽ block `kubectl apply`
trực tiếp lên NetworkPolicy/RBAC từ mọi user không phải ArgoCD SA.

Nếu có incident khẩn cấp cần can thiệp ngay (ví dụ: NetworkPolicy sai đang gây checkout chết,
ArgoCD bị treo chưa sync được), đường duy nhất là break-glass.

**Bài học từ sự cố 16/07/2026 (postmortem 0008):** apply tay không qua review gây 2h 37p downtime.
Break-glass không thay thế GitOps — nó chỉ là khẩn cấp có kiểm soát.

---

## Quy trình break-glass

### Bước 1 — Xác nhận thực sự cần break-glass

Trước khi làm gì, trả lời 3 câu hỏi:

```
1. ArgoCD có thể sync được không?
   → nếu có: mở PR, merge, wait 3 phút, không cần break-glass

2. Có thể revert bằng cách xóa resource sai không?
   → kubectl delete networkpolicy <tên> -n techx-tf3
   → ArgoCD sẽ tạo lại đúng từ Git trong vòng ~3 phút

3. Downtime hiện tại có đủ nghiêm trọng để justify bypass không?
   → checkout dead + ArgoCD không sync được = YES
   → muốn test nhanh = NO
```

### Bước 2 — Thông báo team TRƯỚC khi apply

Gửi message vào channel team (Slack/Discord/...) với nội dung:

```
[BREAK-GLASS] <tên bạn> đang apply tay vào cluster
Lý do: <mô tả ngắn tại sao không thể qua GitOps>
Resource: <loại resource> / <tên> / namespace <ns>
Thời điểm: <HH:MM GMT+7>
```

### Bước 3 — Apply với đúng identity

Break-glass yêu cầu dùng role có quyền write. Hiện tại đường break-glass là qua
`eks_admin_principal_arns` (cluster-admin) — chỉ dùng khi thực sự cần:

```bash
# Đảm bảo đang dùng đúng AWS profile có quyền cluster-admin
aws sts get-caller-identity

# Apply resource
kubectl apply -f <file.yaml> -n techx-tf3

# Verify ngay
kubectl get <resource> -n techx-tf3
```

**Kyverno sẽ block** nếu identity hiện tại là `tf3-production-readonly`. Cần dùng identity có
cluster-admin (xem `eks_admin_principal_arns` trong Terraform state, hoặc contact `arthur`/TL).

### Bước 4 — Verify fix hoạt động

```bash
# Ví dụ với NetworkPolicy
kubectl get networkpolicy -n techx-tf3

# Kiểm tra OTel Collector connect được
kubectl logs -n techx-tf3 -l app.kubernetes.io/name=opentelemetry-collector \
  --tail=20 | grep -E "error|success|opensearch"

# Kiểm tra checkout recovery
kubectl rollout status deploy/checkout -n techx-tf3 --timeout=60s
```

### Bước 5 — Commit vào Git NGAY SAU KHI CLUSTER ỔN ĐỊNH

```bash
git checkout -b fix/break-glass-<incident-id>

# Copy resource hiện tại ra file
kubectl get networkpolicy <tên> -n techx-tf3 -o yaml \
  | grep -v "resourceVersion\|uid\|creationTimestamp\|generation\|managedFields" \
  > gitops/infrastructure/network-policy-<tên>.yaml

git add gitops/infrastructure/network-policy-<tên>.yaml
git commit -m "fix: break-glass sync - <mô tả ngắn>"
git push

# Mở PR ngay, ghi rõ trong description:
# - Incident ID
# - Lý do dùng break-glass
# - Diff so với trước
# - Postmortem sẽ được viết ở đâu
```

### Bước 6 — Viết postmortem

Mọi lần dùng break-glass đều phải có postmortem (dù ngắn):
- File: `docs/postmortem/00XX-break-glass-<ngày>-<mô tả>.md`
- Nội dung tối thiểu: khi nào, ai, lý do, resource gì, timeline, PR số bao nhiêu

---

## Những gì KHÔNG phải break-glass (đừng nhầm)

| Tình huống | Đường đúng | KHÔNG dùng break-glass |
|---|---|---|
| NetworkPolicy sai trong Git | Mở PR fix → merge → ArgoCD tự sync | |
| Muốn test nhanh | `helm template` local, hoặc test trên staging | |
| ArgoCD sync chậm | Check ArgoCD UI, manual sync button | |
| Resource cũ tạo tay cần dọn | `kubectl delete` rồi ArgoCD tạo lại | |

---

## Liên quan

- **Postmortem 0008:** `docs/postmortem/0008-manual-networkpolicy-checkout-browse-disruption.md`
- **RBAC proposal:** `docs/rbac-least-privilege-proposal.md`
- **Kyverno policy:** `gitops/policies/kyverno/audit-sensitive-resources.yaml`
- **ArgoCD infra app:** `gitops/apps/infrastructure-app.yaml` (`orphanedResources: warn: true`)
