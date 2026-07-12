# ADR 0001 — Nâng cấp EKS control plane 1.32 → 1.34 (thoát extended support)

**Ngày:** 10/07/2026
**Người quyết định:** CDO02 (Reliability + Cost Optimization)
**Trạng thái:** 🟡 Đã duyệt hướng — đang thực thi pre-work, **chưa apply lên cluster thật**
**Trụ liên quan:** Cost Optimization (động cơ chính) + Reliability (rủi ro thực thi) + Operational Excellence

---

## Bối cảnh

Cluster `techx-corp-tf3` đang chạy **EKS 1.32** (platform `eks.49`). Xác minh qua
`aws eks describe-cluster-versions` ngày 10/07/2026:

| Version | Trạng thái | Standard support hết | Extended support hết |
|---|---|---|---|
| 1.32 (hiện tại) | **EXTENDED_SUPPORT** | 23/03/2026 (đã qua) | 23/03/2027 |
| 1.33 | STANDARD | 29/07/2026 (sắp hết) | 29/07/2027 |
| **1.34 (target)** | STANDARD | **02/12/2026** | 02/12/2027 |
| 1.35 | STANDARD | 27/03/2027 | 27/03/2028 |
| 1.36 | STANDARD | 02/08/2027 | 02/08/2028 |

**Vấn đề:** 1.32 đã rơi vào **extended support** từ 23/03/2026 → EKS tính phí control
plane **~$0.60/giờ/cluster** thay vì **~$0.10/giờ** ở standard support — đắt **~6 lần**,
cộng dồn liên tục 24/7. Đây là lãng phí chi phí trực tiếp trong trần ~$300/tuần
(`onboarding/BUDGET.md`), có thể cắt được ngay bằng cách lên standard support.

**Ràng buộc kỹ thuật quyết định phạm vi:** EKS **chỉ cho nâng 1 minor version mỗi lần**
và **không hỗ trợ downgrade**. Không thể nhảy thẳng 1.32 → 1.36.

## Quyết định

Nâng lên **1.34** qua **2 hop tuần tự** (1.32 → 1.33 → 1.34), thực thi qua Terraform +
CI pipeline hiện có, **sau khi hoàn tất pre-work bắt buộc** (đặc biệt là REL-01).

## Vì sao 1.34, không phải 1.36

- **1.34 đủ để cắt phí extended** (mục tiêu chính) và có runway standard tới 02/12/2026 —
  đủ dài cho toàn bộ Phase 3.
- **1.36 tốn gấp đôi công + rủi ro**: 4 hop = 4 vòng rolling-replace node = 4 lần rủi ro
  vỡ SLO checkout. Runway dài hơn của 1.36 (tới 08/2027) **không có giá trị trong khung
  3 tuần của Phase 3**.
- **1.33 bị loại** vì standard support sắp hết (29/07/2026) — lên 1.33 rồi sẽ phải nâng
  lại gần như ngay, không đáng.

## Điều kiện tiên quyết bắt buộc (pre-work) — chặn cứng, không bỏ qua

1. **REL-01 (replicas ≥2 + PDB nhóm checkout) PHẢI xong trước hop đầu tiên.** Bằng chứng
   lịch sử: lần nâng 1.31 → 1.32 trước đó **đã gây gián đoạn checkout ngắn** do node
   rolling-replace với `replicas: 1`. Nâng 2 hop = 2 vòng cycle node; không có PDB +
   replica thì gần như chắc chắn vỡ SLO checkout (≥99%) mỗi hop. Managed node group tôn
   trọng PDB khi drain — đây là cơ chế bảo vệ chính.
2. **REL-10 (datastore không PVC): giảm thiểu trước khi cycle node.** Postgres/Kafka/Valkey
   hiện 0 PVC — node cycle có thể mất dữ liệu. Tối thiểu: `pg_dump` logical backup Postgres
   trước mỗi hop + ghi nhận đây là accepted risk trong ADR này.
3. **Quét deprecated API** (`pluto`/`kubent`) trên Helm chart + manifest ArgoCD (nếu nhánh
   `feature/gitops-migration` đã merge) — nhảy 2 version có thể chạm API đã removed.
4. **Bảng addon compatibility** cho 1.33 và 1.34: CoreDNS, kube-proxy, VPC CNI, EBS CSI,
   `aws-load-balancer-controller`.

## Hệ quả

**Tích cực:**
- Cắt phí extended support (~6× → 1× control plane cost) ngay sau hop cuối.
- Buộc phải làm REL-01 trước — vô tình đẩy nhanh 1 mục P0 reliability quan trọng nhất.

**Tiêu cực / rủi ro chấp nhận:**
- **Không downgrade được** — mỗi hop là điểm không quay lại. Giảm thiểu bằng: apply từng
  hop một, smoke test đầy đủ trước khi sang hop tiếp theo.
- Mỗi hop có gián đoạn ngắn khi rolling-replace node → chọn cửa sổ giờ thấp điểm, KHÔNG
  làm trong lúc Pitch/demo.
- **Rủi ro mất dữ liệu datastore** (REL-10 chưa vá triệt để) — chấp nhận với điều kiện có
  `pg_dump` trước mỗi hop.
- Đây là **hạ tầng chung TF3** — cần đồng bộ CDO01 (chủ pipeline apply) và lưu ý xung đột
  với nhánh ArgoCD của họ (nếu chuyển sang ArgoCD quản version thì luồng apply sẽ khác).

## Phương án đã cân nhắc và loại

- **Nhảy thẳng 1.32 → 1.36:** bất khả thi (EKS chỉ nâng 1 minor/lần).
- **Ở lại 1.32:** tiếp tục trả phí extended, không bền vững.
- **Lên 1.36 (4 hop):** loại vì tốn gấp đôi rủi ro mà runway dư thừa ngoài Phase 3.
- **Apply tay bằng `eksctl`/console:** loại — vi phạm nguyên tắc "mọi thay đổi infra qua
  Terraform + CI" đã thiết lập sau các sự cố đè config trước đó.

## Cách thực thi (tóm tắt — chi tiết ở PR)

Đổi `var.cluster_version` trong `infra/` (`variables.tf`, hiện default `1.32`) → PR →
`terraform-plan.yml` review → merge → `terraform-apply.yml` (**gate `production` cần
approve tay**) → apply control plane → verify → rolling-update node group (PDB bảo vệ) →
smoke test (storefront + checkout thật + Grafana + flagd còn sync) → sang hop tiếp theo.

**flagd:** mỗi hop verify lại `values-flagd-sync.yaml` vẫn ghép và flagd sync đúng nguồn
BTC — không được để rớt (vi phạm = disqualify).

## Trạng thái thực thi

- [ ] Pre-work 1 — REL-01 (replicas + PDB)
- [ ] Pre-work 2 — REL-10 mitigation (pg_dump + accepted risk)
- [ ] Pre-work 3 — deprecated API scan
- [ ] Pre-work 4 — addon compatibility matrix (đồng bộ CDO01)
- [ ] Hop 1 — 1.32 → 1.33 (qua production approval gate)
- [ ] Hop 2 — 1.33 → 1.34 (qua production approval gate)

---
*ADR này là quyết định kiến trúc lớn đầu tiên của dự án được ghi lại — mở thư mục
`docs/adr/`. Cập nhật checklist trạng thái sau mỗi bước.*
