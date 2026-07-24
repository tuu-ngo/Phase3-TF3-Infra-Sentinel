# Postmortem 0013 — Thay đổi ForceNew trên bastion dùng chung bị apply kèm trong một lần `terraform apply` không liên quan → replace bastion + team mất đường SSM (23/07/2026)

**Ngày:** 23/07/2026 (viết ngay sau khi truy vết xong)
**Người xử lý:** CDO02 (Huu Tai Ngo) — chẩn đoán & khắc phục
**Nguồn gốc thay đổi:** commit `2cf73c2` (nvtank, PM-126 baseline hardening) — mã hoá root volume bastion
**Người kích hoạt:** GitHub user `hailv1209` — dispatch `terraform apply` cho resource Mandate #12
**Mức độ ảnh hưởng:** **KHÔNG ảnh hưởng khách hàng.** Storefront/luồng ra tiền không đụng. Ảnh hưởng nội bộ:
mọi thành viên mất đường **SSM vào EKS** vì runbook/script trỏ bastion ID cũ đã bị terminate. EKS API vẫn
sống; đường Cloudflare Zero Trust vẫn còn.
**Trạng thái:** ✅ Đã khắc phục — bastion mới chạy khỏe (SSM Online); runbook/script chuyển sang tra ID động
(PR #371, đã merge vào `main`).

---

## TL;DR

Commit `2cf73c2` (nvtank, 22/07) thêm `root_block_device { encrypted = true }` vào `aws_instance.bastion`
để đóng PM-126. Trên `aws_instance`, đổi mã hoá root volume là thuộc tính **ForceNew** → Terraform lên kế
hoạch `-/+ replace` (destroy + create). Resource chỉ có `lifecycle { ignore_changes = [ami] }`, **không có
`prevent_destroy`**, nên không có gì chặn.

Diff này nằm chờ trên `main`. Sáng 23/07, `hailv1209` dispatch `terraform apply` để tạo resource cho Mandate
#12. `terraform apply` áp lên **toàn bộ state**, không chỉ phần của người bấm — nên nó thực thi luôn diff
ForceNew của nvtank: **terminate bastion cũ `i-02a8d3e39b87180ce` (04:15:12Z), tạo bastion mới
`i-0f5959afa0eb31e7c` (04:16:28Z)**. Run đó cuối cùng **fail** (ở nhánh graph khác), nhưng bastion nằm ở nhánh
riêng nên đã được xử lý xong trước khi lỗi. Hậu quả: instance ID đổi → mọi runbook/script hardcode ID cũ báo
`TargetNotConnected`, team không SSM vào cluster được. Lời khai của `hailv1209` ("không đụng bastion, đó là
code người khác, apply thì chạy tất cả") **khớp hoàn toàn với bằng chứng git**.

---

## When — Timeline (UTC)

- **2026-07-22 15:20:37Z** — nvtank commit `2cf73c2` "fix(iac): resolve PM-126 high-critical baseline", thêm
  `root_block_device { encrypted = true }` vào `infra/modules/access/main.tf` (bastion). `git grep root_block_device
  2cf73c2^` xác nhận block này **không tồn tại ở commit cha** → do đúng commit này tạo ra. Merge vào `main`.
- **2026-07-23 01:44:15Z** — `VietSory` dispatch `terraform apply` (run 29972575137) — **success**, không liên
  quan bastion (loại trừ khỏi nghi vấn).
- **2026-07-23 04:12:14Z** — `hailv1209` dispatch `terraform apply` (run 29978951249, `workflow_dispatch`, trên
  `main`, SHA `5511bedb`). `git merge-base --is-ancestor 2cf73c2 5511bedb` = **YES** → SHA này đã chứa sẵn diff
  ForceNew của nvtank.
- **04:14:39Z** — runner assume OIDC role `techx-corp-tf3-gha-terraform-apply`.
- **04:15:12Z** — Terraform (v1.15.4) `TerminateInstances` bastion cũ `i-02a8d3e39b87180ce` (CloudTrail:
  `previousState=running → shutting-down`).
- **04:16:28Z** — `RunInstances` tạo bastion mới `i-0f5959afa0eb31e7c`.
- **(sau đó)** — run 29978951249 kết thúc **conclusion=failure** (dừng ở resource khác trong graph; xác nhận
  bằng `gh api .../runs/29978951249`). Bastion đã replace xong trước điểm fail.
- **(cùng ngày)** — thành viên báo "SSM không vào được". CDO02 truy vết: bastion cũ `terminated`, bastion mới
  Online → cập nhật runbook/script sang tra ID động (PR #371) → **merged `main` 04:38:26Z**.

---

## Why — Nguyên nhân gốc

**Một thay đổi ForceNew trên tài nguyên hạ tầng dùng chung nằm chờ trên `main`, rồi bị apply bởi người làm
việc không liên quan.** Ba yếu tố cộng hưởng:

1. **ForceNew không được nhận diện/bảo vệ.** `encrypted = true` trên `root_block_device` của `aws_instance` là
   thuộc tính buộc replace. Bản thân việc bật mã hoá là đúng (PM-126), nhưng nó biến một hardening tưởng "vá tại
   chỗ" thành **destroy + create** một tài nguyên mà nhiều người phụ thuộc. Resource **không có `prevent_destroy`**
   → không có bước dừng bắt buộc trước khi xoá.

2. **`terraform apply` là thao tác trên toàn state.** Ai chạy apply cũng "thừa hưởng" mọi diff đang treo trên
   `main`, kể cả của người khác, kể cả ForceNew. `hailv1209` apply cho Mandate #12 nhưng vô tình thực thi luôn
   diff bastion của nvtank. Đây là **lỗ hổng quy trình**, không phải lỗi thao tác của người apply.

3. **Runbook/script hardcode instance ID.** Bastion ID `i-02a8d3e39b87180ce` được nhúng cứng trong 5 file
   (runbook member, `kube-tunnel.sh`, `ACCESS_GUIDE.md`, `private-access-to-ops-uis.md`, `CLAUDE.md`). Bất kỳ
   lần replace nào cũng làm toàn bộ đường SSM của team chết cùng lúc → khuếch đại một thay đổi hạ tầng bình
   thường thành sự cố mất truy cập diện rộng.

**Đã được cảnh báo trước:** trong phiên trước lần apply, đã ghi rõ *"plan sẽ hiện `-/+ replace` trên bastion…
thay xong thì instance ID đổi → lệnh SSM tunnel trong CLAUDE.md và runbook thành sai"*. Cảnh báo có, nhưng
không có cơ chế chặn (prevent_destroy / plan-gate) để biến cảnh báo thành hành động bắt buộc.

---

## Impact

- **Khách hàng:** **không.** Bastion là đường truy cập vận hành (ops), không nằm trong luồng phục vụ. Storefront,
  checkout, browse, cart không bị đụng. EKS API private vẫn hoạt động bình thường.
- **Nội bộ:** thành viên không SSM vào EKS được cho tới khi phát hiện ID đổi. Đường dự phòng **Cloudflare Zero
  Trust** (`kubectl.arthur-ngo.org`, Grafana/Jaeger/ArgoCD UI) không phụ thuộc bastion → vẫn vào được.
- **Dữ liệu:** không mất. Bastion không lưu state; volume mới được tạo có mã hoá (mục tiêu PM-126 vẫn đạt).
- **Hạ tầng Mandate #12:** run apply **fail giữa chừng** → một phần resource Mandate #12 có thể **chưa được
  apply**. State có khả năng ở trạng thái dở dang — cần đối chiếu (xem Action item 5).

---

## Detection & Response — Điều làm ĐÚNG / SAI

**Đúng:**
- Truy vết bằng **bằng chứng cứng, không theo trí nhớ**: CloudTrail (`TerminateInstances`/`RunInstances` + role +
  giờ), `gh` (actor + SHA + conclusion của run), `git show`/`git merge-base`/`git grep` (commit nào thêm block,
  có ở commit cha không, có nằm trong SHA đã apply không).
- Phân định đúng **nguyên nhân gốc (nvtank/PM-126)** vs **người kích hoạt (hailv1209)** — không quy oan người bấm
  apply. Đối chiếu khớp lời khai của họ.
- Khắc phục hệ quả tận gốc thay vì vá tạm: chuyển sang **tra ID động** để miễn nhiễm với mọi lần replace sau
  (PR #371), thay vì chỉ thay ID mới vào file (sẽ hỏng lại lần sau).

**Sai / thiếu:**
- (Quy trình) Không có plan-gate cảnh báo/chặn `-/+ replace` trên tài nguyên quan trọng trước khi apply.
- (Quy trình) Để một diff ForceNew treo trên `main` nhiều giờ; người merge ForceNew không apply ngay/không thông báo.
- (Tài liệu) Hardcode instance ID trong toàn bộ tài liệu truy cập → single point of failure cho đường SSM.
- (Bảo vệ tài nguyên) Bastion thiếu `prevent_destroy` dù là hạ tầng dùng chung.

---

## Action items

1. **[Infra owner — bắt buộc] Thêm `prevent_destroy = true`** cho `aws_instance.bastion` (và các tài nguyên vận
   hành dùng chung khác nếu có). ForceNew về sau sẽ khiến `apply` **fail có chủ đích** thay vì âm thầm replace,
   buộc con người xử lý tường minh (targeted apply có cửa sổ bảo trì).
2. **[CI/CD] Plan-gate cho replace/destroy.** `terraform-apply.yml` nên chặn (hoặc đòi xác nhận thủ công) khi
   plan chứa `-/+`/`destroy` trên tài nguyên gắn nhãn critical (bastion, EKS, datastore). Không để apply thường
   "cuốn" theo thay đổi phá huỷ.
3. **[Quy trình] `main` phải "apply-clean" trước khi apply việc khác.** Ai merge một thay đổi ForceNew/replace
   vào `main` thì **tự apply ngay** trong cửa sổ có kiểm soát + thông báo; không để diff phá huỷ nằm chờ người
   khác vô tình apply. Cân nhắc `terraform plan -target` cho thay đổi hạ tầng nhạy cảm.
4. **[CDO02 — ĐÃ XONG] Bỏ hardcode bastion ID** khỏi runbook/script, chuyển sang tra động theo tag
   `Name=techx-corp-tf3-bastion` + resolve EKS endpoint theo tên cluster. PR #371 đã merge `main`.
5. **[Mandate #12 owner — theo dõi] Đối chiếu state sau run fail.** Run 29978951249 (`hailv1209`) fail giữa
   chừng → chạy `terraform plan` xác định resource Mandate #12 nào **chưa apply**, hoàn tất trong một apply có
   kiểm soát. Xác nhận không có tài nguyên nào ở trạng thái nửa vời.
6. **[Tài liệu] Cập nhật mọi tham chiếu bastion** sang "ID không cố định — tra động"; ID hiện tại
   `i-0f5959afa0eb31e7c` chỉ ghi làm ví dụ, không nhúng cứng.

---

## Liên quan

- Postmortem [0008](0008-ssm-bastion-to-cloudflare-zero-trust-retrospective.md) — bastion SSM & đường Cloudflare Zero Trust.
- PR [#371](https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel/pull/371) — runbook/script tra bastion ID động (khắc phục hệ quả).
- Runbook [`member-readonly-ssm-access.md`](../runbooks/member-readonly-ssm-access.md) — đường SSM vào EKS (đã cập nhật).
- Commit `2cf73c2` (nvtank, PM-126) — nguồn thay đổi ForceNew trên `infra/modules/access/main.tf`.
