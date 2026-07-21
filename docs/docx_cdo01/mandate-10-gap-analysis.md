# [MANDATE 10] Audit hiện trạng CI/CD Supply-Chain & Gap Analysis

**Ngày thực hiện:** 20/07/2026
**Phạm vi:** Kiểm toán quy trình CI/CD và chuỗi cung ứng so với 6 yêu cầu bảo mật của Directive #10.

---

## 1. Đính chính quan trọng về Branch Protection trên nhánh `main`

> [!WARNING]
> Kết luận sơ bộ vào sáng 20/07 rằng "chưa có branch protection trên main" là **SAI LỆCH** do hạn chế về quyền hiển thị của GitHub API, không phải do hệ thống thiếu cấu hình.

**Bằng chứng đính chính:**
Thông qua hình ảnh thực tế từ quá trình merge **PR #273** (do anh tuu-ngo merge vào main), đã xác nhận rõ ràng các cơ chế bảo vệ sau **ĐÃ HOẠT ĐỘNG**:
- *"Review required — At least 1 approving review is required by reviewers with write access"*
- *"Merging is blocked"* (cho tới khi đủ điều kiện approve)
- *"All checks have passed — 1 successful check"* (có ít nhất 1 required status check chặn merge)

**Nguyên nhân gây hiểu lầm từ API:**
Khi dùng token của tài khoản `hoang-trong-tan` gọi endpoint `gh api repos/tuu-ngo/Phase3-TF3-Infra-Sentinel/branches/main/protection`, GitHub API trả về mã lỗi **404 Not Found**. Đây là hành vi bảo mật mặc định của GitHub: API sẽ trả về 404 (thay vì 403 Forbidden) nếu caller không có quyền Admin trên repo, nhằm tránh làm lộ sự tồn tại của cấu hình.
👉 **Bài học rút ra:** Không dùng mã 404 từ API của một tài khoản non-admin làm bằng chứng phủ định sự tồn tại của Branch Protection. Cần xác nhận trực tiếp qua giao diện `Settings -> Branches` bởi người có quyền Admin.

---

## 2. Bảng Gap Analysis chi tiết (so với 6 yêu cầu)

### Yêu cầu 1: Cổng chặn thật CI đỏ
> *Yêu cầu: PR hỏng build, hỏng test, dính lỗi bảo mật nghiêm trọng (HIGH/CRITICAL) thì phải chặn không cho merge.*

- **Trạng thái:** ✅ Đã có thật.
- **Hiện trạng / Bằng chứng:** Như đã đính chính ở phần 1, nhánh `main` đã bật "Require status checks to pass before merging". Cổng chặn đã kích hoạt.
- **Gap (Thông tin cần bổ sung):**
  > [!NOTE]
  > Cần người có quyền Admin xác nhận trực tiếp (từ giao diện `Settings -> Branches`) **danh sách chính xác** các workflow nào đang được cấu hình làm *Required Check*. Hiện chưa rõ tính năng chặn merge chỉ áp dụng cho bước "Build", hay đã áp dụng bắt buộc cho cả "Trivy" và "Secret Scan".

### Yêu cầu 2: Scan HIGH/CRITICAL chặn merge
> *Yêu cầu: Không đẩy rác vào production. Cần scan lỗ hổng.*

- **Trạng thái:** 🟡 Đạt 1 phần.
- **Hiện trạng / Bằng chứng:**
  - **Trivy:** Đã có (quét trước và sau khi push, dùng cờ chặn `exit-code 1` tại `build-push-ecr.yml`). ✅
  - **Secret Scan:** Đã có (dùng `gitleaks` trong `secret-scan.yml`, chạy trên sự kiện push và PR vào `main`). ✅
  - *(Ghi chú: Giống Yêu cầu 1, cần Admin xác nhận xem Trivy và Secret Scan có đang được tick chọn làm Required Status Check hay chỉ chạy để tham khảo).*
- **Gap cần khắc phục:**
  - **IaC Misconfig Scan (Terraform):** ❌ Chưa có. Workflow `terraform-plan.yml` hiện tại chỉ chạy `fmt -check`, `validate` và `plan`, nhưng hoàn toàn chưa có bước dùng `tfsec` hay `Checkov` để quét lỗi bảo mật hạ tầng.
  - **SAST (Static Application Security Testing):** ❌ Chưa có workflow nào thực hiện quét mã nguồn.

### Yêu cầu 3: Bất biến + xác thực nguồn gốc
> *Yêu cầu: Build ra artifact phải ký. Deploy phải check chữ ký. Image không bị tráo đổi.*

- **Trạng thái:** 🟡 Đạt 1 phần.
- **Hiện trạng / Bằng chứng:**
  - **Ký số & Digest:** Đã có Cosign keyless sign+verify. Đã có bắt buộc ECR digest resolve. ✅
- **Gap cần khắc phục:**
  - **SBOM (Software Bill of Materials):** ❌ Chưa có bước nào tạo SBOM.
  - **Kyverno verifyImages:** ❌ Chưa enforce admission. Ticket PM-114 vẫn đang nằm ở trạng thái "To Do" kể từ lúc làm Mandate 5.

### Yêu cầu 4: Pin theo SHA/digest
> *Yêu cầu: Action bên thứ 3 trong workflow phải dùng commit SHA, không xài tag v2, v3.*

- **Trạng thái:** ❌ Chưa đạt (Toàn bộ).
- **Hiện trạng / Bằng chứng:** Qua rà soát cả 6 workflow (`.github/workflows/*.yml`), 100% các từ khóa `uses:` đều đang pin theo tag version (ví dụ: `actions/checkout@v3`, `docker/login-action@v2`). Không có action nào đang pin cứng bằng commit SHA.
- **Gap cần khắc phục:** Đổi toàn bộ `uses` trong các file YAML sang định dạng commit SHA.

### Yêu cầu 5: Truy ngược được
> *Yêu cầu: Tìm được artifact X sinh ra từ commit Y do workflow Z chạy lúc nào.*

- **Trạng thái:** 🟡 Đạt 1 phần.
- **Hiện trạng / Bằng chứng:** Dữ liệu thô thực chất đã được sinh ra và lưu lại (các file `approved-images.json`, báo cáo `release-evidence/cosign/*.json`...). ✅
- **Gap cần khắc phục:** Dữ liệu vẫn đang rời rạc. Cần có một kịch bản/runbook hoặc script gộp thống nhất thành 1 luồng tra cứu rõ ràng để team vận hành dễ dàng đối chiếu.

### Yêu cầu 6: Chỉ đụng cái gì đổi
> *Yêu cầu: Tối ưu CI, không build lại toàn bộ nếu chỉ đổi 1 module.*

- **Trạng thái:** ✅ Đã đạt hoàn toàn.
- **Hiện trạng / Bằng chứng:** Đã có sẵn job `prepare` trong workflow, thực hiện lệnh `git diff` theo ngữ cảnh (scoped build) để tìm và chỉ build đúng những service có thay đổi mã nguồn.

---

## 3. Tổng kết Hành động (Next Steps)

1. **[Quyền Admin]** Yêu cầu Admin vào xem `Settings -> Branches` và xác nhận danh sách Required Status Checks thật sự.
2. Cập nhật các file YAML trong `.github/workflows/`:
   - Bổ sung `tfsec` hoặc `Checkov` vào `terraform-plan.yml`.
   - Cập nhật toàn bộ các thẻ `uses:` từ Tag Version sang Commit SHA.
3. Giải quyết nốt PM-114 (Kyverno verifyImages) và cân nhắc thêm bước sinh SBOM.
