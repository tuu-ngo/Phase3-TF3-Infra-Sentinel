# [MANDATE 10] Audit hiện trạng CI/CD Supply-Chain & Gap Analysis

> [!WARNING]
> **HISTORICAL SNAPSHOT - SUPERSEDED**
> Báo cáo này là ảnh chụp hiện trạng (snapshot) ngày 20/07/2026. Do nhánh hiện tại đã được cập nhật với `main`, nhiều Gap dưới đây **đã được giải quyết** trong thực tế (tfsec, Semgrep, immutable pins, SBOM, Kyverno verifyImages, trace-provenance.sh đều đã có). Vui lòng xem tài liệu này như một tài liệu lịch sử.

**Ngày thực hiện ban đầu:** 20/07/2026
**Phạm vi:** Kiểm toán quy trình CI/CD và chuỗi cung ứng so với 6 yêu cầu bảo mật của Directive #10.

---

## 1. Ghi chú về Branch Protection trên nhánh `main`

**Bằng chứng đính chính:**
Thông qua hình ảnh thực tế từ quá trình merge **PR #273** (do anh tuu-ngo merge vào main), đã xác nhận rõ ràng các cơ chế bảo vệ sau có hoạt động:
- *"Review required — At least 1 approving review is required by reviewers with write access"*
- *"Merging is blocked"* (cho tới khi đủ điều kiện approve)

**Nguyên nhân gây hiểu lầm từ API:**
Khi dùng token gọi endpoint GitHub API kiểm tra protection, kết quả trả về mã lỗi **404 Not Found**. Không thể khẳng định GitHub cố ý trả 404; chỉ có thể kết luận rằng mã 404 là **ambiguous (không rõ ràng)** khi token thiếu quyền `Administration: read`. Yêu cầu xác nhận bằng cấu hình export chính xác thay vì đoán mò.

---

## 2. Bảng Gap Analysis chi tiết (so với 6 yêu cầu)

### Yêu cầu 1: Cổng chặn thật CI đỏ
> *Yêu cầu: PR hỏng build, hỏng test, dính lỗi bảo mật nghiêm trọng (HIGH/CRITICAL) thì phải chặn không cho merge.*

- **Trạng thái:** ✅ Đã hoàn thành (Có đủ bằng chứng).
- **Hiện trạng / Bằng chứng:** Nhánh `main` đã bật chặn merge. Đã có bằng chứng thực tế chứng minh:
  1. **Ảnh chặn merge (Intentional Red PR):** `docs/evidence/mandate-10/intentional-red-pr-blocked.png`
  2. **Cấu hình Export từ API:** `docs/evidence/mandate-10/branch-protection.json` (Xác nhận `Secure delivery gate` là check bắt buộc).
- **Gap:** Không còn gap. Yêu cầu 1 đã thỏa mãn hoàn toàn.

### Yêu cầu 2: Scan HIGH/CRITICAL chặn merge
> *Yêu cầu: Không đẩy rác vào production. Cần scan lỗ hổng.*

- **Trạng thái (Snapshot 20/07):** 🟡 Đạt 1 phần.
- **Hiện trạng / Bằng chứng:**
  - **Trivy Image Scan:** Hiện đang chạy trên sự kiện push vào `main` hoặc chạy `manual`, **không phải** là cổng chặn pre-merge trên PR (PR pre-merge gate).
  - **Secret Scan:** Đã có.
- **Gap (Đã được khắc phục trên main):**
  - Trước đây thiếu IaC Misconfig Scan và SAST. Hiện tại **tfsec** và **Semgrep** đã có trong Secure delivery.

### Yêu cầu 3: Bất biến + xác thực nguồn gốc
> *Yêu cầu: Build ra artifact phải ký. Deploy phải check chữ ký. Image không bị tráo đổi.*

- **Trạng thái (Snapshot 20/07):** 🟡 Đạt 1 phần.
- **Gap (Đã được khắc phục trên main):**
  - CycloneDX SBOM và Cosign attestations đã được triển khai.
  - Kyverno `verifyImages` policy hiện đã có ở chế độ Audit.

### Yêu cầu 4: Pin theo SHA/digest
> *Yêu cầu: Action bên thứ 3 trong workflow phải dùng commit SHA, không xài tag v2, v3.*

- **Trạng thái (Snapshot 20/07):** ❌ Chưa đạt.
- **Gap (Đã được khắc phục trên main):** GitHub Actions và Dockerfile bases hiện đã được pin immutable.

### Yêu cầu 5: Truy ngược được
> *Yêu cầu: Tìm được artifact X sinh ra từ commit Y do workflow Z chạy lúc nào.*

- **Trạng thái (Snapshot 20/07):** 🟡 Đạt 1 phần.
- **Gap (Đã được khắc phục trên main):** Script `trace-provenance.sh` đã có sẵn. Yêu cầu duy nhất còn lại là cần chạy script này để lấy **live trace evidence**.

### Yêu cầu 6: Chỉ đụng cái gì đổi
> *Yêu cầu: Tối ưu CI, không build lại toàn bộ nếu chỉ đổi 1 module.*

- **Trạng thái:** ✅ Đã đạt hoàn toàn (có job `prepare` tính toán scope).
- **Lưu ý về Argo:** Các tài nguyên unmanaged có thể được ArgoCD phát hiện là orphaned (mồ côi), nhưng **không được self-heal/prune tự động**.

---

## 3. Tổng kết Hành động (Next Steps)

1. Cung cấp bằng chứng cho Yêu cầu 1: ~~Export danh sách required-check và tạo `intentional-red-PR` để chứng minh cổng chặn.~~ (Đã làm xong)
2. Chạy `trace-provenance.sh` để lấy live trace evidence cho Yêu cầu 5.
3. Đảm bảo Trivy scan chạy như một pre-merge gate trên PR, thay vì chỉ chạy trên `main`.
4. Các sửa đổi khác theo review (nếu thuộc phạm vi PR này):
   - Tách `docs/research-security-mechanisms.md` sang PR khác.
   - Sửa NetworkPolicy ingress/egress semantics và AWS VPC CNI source.
   - Đảm bảo xóa mọi reference đến "claim finalizer" nếu không có evidence.
   - Không khuyến nghị mặc định map break-glass role vào `system:masters`.
   - Resolve 4 review threads và chạy lại toàn bộ current-main checks sau khi rebase.
