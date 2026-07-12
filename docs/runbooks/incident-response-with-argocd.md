# Runbook — Xử lý sự cố khi cluster do ArgoCD quản (GitOps)

**Áp dụng cho:** namespace `techx-tf3`, các Application ArgoCD (`techx-corp`, `techx-infrastructure-app`).
**Vấn đề runbook này giải quyết:** ArgoCD `selfHeal: true` sẽ tự động revert mọi thay đổi
thủ công về đúng trạng thái trong Git. Khi có sự cố cần containment tay (scale, patch,
restart, cô lập service), nếu không xử lý đúng, ArgoCD sẽ **undo cái vá của bạn** →
sự cố quay lại. Runbook này là cách làm đúng.

---

## TL;DR — thứ tự bắt buộc (KHÔNG đảo)

```
1. PAUSE      argocd app set techx-corp --sync-policy none
2. FIX        sửa tay trên cluster để chặn sự cố (scale/patch/restart/cô lập)
3. GHI LẠI    chép chính xác đã làm gì + giờ (cho postmortem)
4. UPDATE GIT đưa đúng cái vừa sửa vào Git, verify Git == cluster
5. RE-ENABLE  argocd app set techx-corp --sync-policy automated
```

**Git phải khớp cluster TRƯỚC khi bật lại (bước 4 xong mới làm bước 5).**

---

## Vì sao thứ tự này

ArgoCD `selfHeal` = "kéo cluster về đúng Git". `prune` = "xóa cái không có trong Git".
Cặp `automated` chạy nền, reconcile mỗi ~3 phút. Trong lúc sự cố:
- Nếu để nguyên auto-sync → thao tác tay của bạn bị revert trong vài phút.
- Nếu tắt auto-sync (`--sync-policy none`) → cả selfHeal lẫn prune tạm ngừng, bạn được
  toàn quyền thao tác tay để chặn sự cố ngay.

## 🪤 Hai bẫy làm hỏng pattern

**Bẫy 1 — bật lại TRƯỚC khi update Git (nguy hiểm nhất).**
Nếu bật auto-sync khi Git vẫn là trạng thái cũ đang lỗi → ArgoCD thấy cluster (đã vá) ≠
Git (chưa vá) → `selfHeal` **revert ngay cái vá của bạn** → sự cố quay lại lập tức.
→ Quy tắc cứng: **codify vào Git + verify Git == cluster xong mới bật lại.**

**Bẫy 2 — quên bật lại.**
Pause xong, xử lý xong, quên bước 5 → GitOps âm thầm mất tác dụng, drift tích tụ, người
sau tưởng ArgoCD đang quản mà không.
→ **"Re-enable ArgoCD" là mục bắt buộc trong checklist đóng sự cố.** Sự cố chưa closed
nếu auto-sync chưa bật lại.

## Lệnh cụ thể

```bash
# Kiểm tra sync policy hiện tại
argocd app get techx-corp -o json | jq '.spec.syncPolicy'

# 1. PAUSE (tắt cả auto-sync + selfHeal + prune)
argocd app set techx-corp --sync-policy none

# 2-3. Containment tay + ghi lại (ví dụ)
kubectl -n techx-tf3 scale deploy/checkout --replicas=4      # ví dụ chặn quá tải
#   -> GHI: "14:22 scale checkout 2->4 để hạ latency spike"

# 4. Codify vào Git: sửa values-prod.yaml / manifest cho khớp, commit, push, để ArgoCD
#    đã trỏ main tự thấy. Verify không còn diff:
argocd app diff techx-corp        # phải rỗng (Git == cluster) trước khi qua bước 5

# 5. RE-ENABLE
argocd app set techx-corp --sync-policy automated
```

> Nếu không có `argocd` CLI, làm tương đương bằng `kubectl -n argocd patch application
> techx-corp --type merge -p '{"spec":{"syncPolicy":{"automated":null}}}'` để pause, và
> patch lại `{"automated":{"selfHeal":true,"prune":false}}` để bật.

## Lưu ý cấu hình đi kèm (quyết định của team, xem ADR GitOps khi có)

- Giai đoạn đầu (hệ thống còn giòn, datastore 0 PVC): để **`prune: false`** — tránh
  ArgoCD tự xóa nhầm resource khi render Helm lệch. `selfHeal` sai thì hoàn nguyên;
  `prune` sai thì phá hủy. Bật `prune: true` khi hệ thống đã hardening + tin pipeline.
- Với resource runtime-mutable (VD replicas do HPA đổi khi có HPA): thêm
  `ignoreDifferences` để ArgoCD không đánh nhau với HPA.

## Ghi công / audit
Cặp "thao tác tay (bước 2-3) + commit codify (bước 4)" chính là audit trail cho
postmortem — ghi lại đầy đủ giờ, người thực hiện, lý do.
