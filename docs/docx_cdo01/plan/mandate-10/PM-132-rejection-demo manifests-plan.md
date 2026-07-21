# Kế hoạch triển khai PM-132: Chuẩn bị 3 kịch bản demo và viết báo cáo/ADR cho Mandate 10

## 1. Task này làm gì? Phải làm gì?
Mục tiêu của task PM-132 là **đóng gói toàn bộ công sức của Epic Mandate 10 thành các kịch bản nghiệm thu cụ thể và tài liệu báo cáo chính thức**. 
Bạn **không** cần phải code thêm tính năng mới ở task này. Bạn chỉ cần thiết lập 3 kịch bản có sẵn để "diễn" trước mặt mentor, chứng minh rằng các hệ thống chặn (gate) và truy vết (traceability) mà bạn đã làm ở các task trước (PM-125, PM-127, PM-129) hoạt động chính xác. Cuối cùng, bạn sẽ viết 2 file tài liệu (Báo cáo tổng kết và Bản ghi quyết định kiến trúc - ADR) để Mentor ký duyệt.

---

## 2. Làm như thế nào? Chi tiết từng thao tác và lệnh

### 🛠️ Kịch bản Demo 1: PR cố tình đỏ (Chặn merge tại CI)
**Mục đích:** Chứng minh nếu code chứa lỗ hổng bảo mật (SAST/Secret) hoặc sai cấu hình hạ tầng (IaC), Github Actions sẽ báo đỏ và nút Merge sẽ bị khóa cứng.

**Các bước thao tác:**
1. Mở Terminal, tạo một nhánh mới:
   ```bash
   git checkout -b demo/mandate-10-ci-gate
   ```
2. Mở file mã nguồn bất kỳ (ví dụ: `phase3 - information/techx-corp-platform/src/checkout/main.go`) và thêm một đoạn comment chứa Fake AWS Key để bẫy Secret Scanner:
   ```go
   // TODO: Remove this fake key later
   // AWS_ACCESS_KEY_ID="AKIAIOSFODNN7EXAMPLE"
   // AWS_SECRET_ACCESS_KEY="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
   ```
3. (Tùy chọn) Sửa file `infra/live/production/main.tf` để tạo ra một cấu hình hớ hênh (ví dụ mở port `0.0.0.0/0`) để bẫy IaC Scanner (Trivy/tfsec).
4. Lưu file, commit và push lên Github:
   ```bash
   git add .
   git commit -m "chore: inject fake secret for CI gate demo"
   git push origin demo/mandate-10-ci-gate
   ```
5. Lên trình duyệt Github, bấm tạo Pull Request (PR) từ nhánh này vào `main`.
6. **Lúc demo:** Chỉ cần mở sẵn link URL của PR này cho mentor xem. Mentor sẽ thấy CI chạy lỗi (`Exit 1`) và nút **Merge pull request** chuyển sang màu xám không thể bấm được.

---

### 🛠️ Kịch bản Demo 2: Cổng chặn Kubernetes (Image chưa ký)
**Mục đích:** Chứng minh nếu ai đó cố tình deploy một file cấu hình trỏ tới một image không có chữ ký Cosign hợp lệ, Kyverno sẽ từ chối ngay lập tức tại cổng API của Cluster.

**Các bước thao tác:**
1. Tạo một thư mục chứa dữ liệu demo nếu chưa có:
   ```bash
   mkdir -p docs/evidence/mandate-10/rejection-demo
   ```
2. Tạo file `docs/evidence/mandate-10/rejection-demo/bad-unsigned-image.yaml` với nội dung sau:
   ```yaml
   apiVersion: apps/v1
   kind: Deployment
   metadata:
     name: unsigned-demo
     namespace: techx-tf3
   spec:
     replicas: 1
     selector:
       matchLabels:
         app: unsigned-demo
     template:
       metadata:
         labels:
           app: unsigned-demo
       spec:
         containers:
         - name: app
           # Sử dụng một image/digest giả hoặc một image từ Docker Hub không do TechX ký
           image: 197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp@sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef
   ```
3. **Lúc demo:** Mở Terminal và đưa mentor lệnh này để họ tự gõ/copy-paste:
   ```bash
   kubectl apply --dry-run=server -f docs/evidence/mandate-10/rejection-demo/bad-unsigned-image.yaml
   ```
4. **Kết quả mong đợi:** Lệnh trên sẽ bắn ra lỗi văng chữ đỏ: `Error from server: admission webhook ... denied the request... image verification failed`.

---

### 🛠️ Kịch bản Demo 3: Truy ngược Provenance (Truy vết nguồn gốc)
**Mục đích:** Chỉ vào 1 pod bất kỳ đang chạy, bấm 1 nút và xuất ra thông tin: Pod này chạy image nào? Code sinh ra từ Commit nào? Ai duyệt Pull Request đó? Có pass scan bảo mật không? Chữ ký và SBOM đâu?

**Các bước thao tác:**
1. Tìm tên của một Pod đang chạy khỏe mạnh:
   ```bash
   kubectl -n techx-tf3 get pods
   ```
   *(Ghi chú lại tên pod, ví dụ: `checkout-7c98f5b8d-abcde`)*
2. **Lúc demo:** Chạy lệnh script truy vết mà bạn đã viết ở task PM-129, trỏ thẳng vào Pod đó:
   ```bash
   bash scripts/ci/trace-provenance.sh techx-tf3 checkout-7c98f5b8d-abcde
   ```
3. **Kết quả mong đợi:** Script sẽ chạy mượt mà, gọi API lên Github/ECR và in ra màn hình chuỗi mắt xích 5 bước (Digest -> Commit -> PR -> Scan -> Cosign/SBOM).

**🔍 Hướng dẫn chi tiết cách tự test (Dry-run) ở nhà:**
Để tránh lỗi (crash) lúc demo trực tiếp, bạn cần kiểm tra trước 3 điều kiện sau trên máy tính của mình:
- **Cài đặt đủ công cụ (CLI Tools):** Mở Terminal và gõ thử `jq --version`, `curl --version`, và `gh --version`. Nếu lệnh nào báo `command not found`, bạn cần cài đặt ngay (Ví dụ dùng `choco install jq gh` trên Windows hoặc cài đặt thủ công).
- **Đăng nhập Github CLI (Auth Token):** Chạy lệnh `gh auth status` để đảm bảo Terminal của bạn đã được kết nối với tài khoản Github có quyền đọc repository. Nếu chưa, hãy chạy `gh auth login` và làm theo hướng dẫn.
- **Xác thực AWS CLI:** Đảm bảo bạn đã export đúng profile (chạy lệnh `export AWS_PROFILE=techx-corp` hoặc set environment variable) và chắc chắn lệnh `aws sts get-caller-identity` không báo lỗi Access Denied.
- **Chạy thử ít nhất 1 lần:** Chạy chính xác lệnh `bash scripts/ci/trace-provenance.sh techx-tf3 checkout-7c98f5b8d-abcde` trên máy tính của bạn trước. Việc này giúp bạn biết script mất bao nhiêu giây để load (vì gọi nhiều API), đồng thời kiểm tra format log in ra có bị lỗi font hay xuống dòng bất thường không.

---

### 📝 Viết Báo Cáo & ADR

#### 1. Báo cáo (Report)
Tạo file `docs/docx_cdo01/mandate-10-secure-delivery-report.md`. 
Copy y hệt cấu trúc của báo cáo Mandate 5, nhưng đổi nội dung để đối chiếu 6 yêu cầu của Mandate 10.
- Phần *Cơ sở kỹ thuật*: Liệt kê file workflows `build-push-ecr.yml`, `terraform-plan.yml`, v.v.
- Phần *Nghiệm thu*: Điền ĐẠT cho tất cả 6 tiêu chí (Gắn kèm link URL của PR demo).

#### 2. ADR (Bản ghi quyết định kiến trúc)
Tạo file `docs/adr/0011-mandate-10-secure-delivery-pipeline.md`.
Nội dung bắt buộc phải có:
- **Context:** Cần thắt chặt CI/CD để không tin tưởng mù quáng image đẩy lên.
- **Decision:** Đã quyết định dùng: Trivy (cho IaC), Semgrep (cho SAST), Cosign Keyless (Ký image), CycloneDX (SBOM), và Kyverno verifyImages. Toàn bộ GitHub Action pin theo SHA.
- **Scope:** Repostiory hiện tại và cluster `techx-tf3`.
- **Exceptions:** (Nếu có, ví dụ có 1 base image bên thứ 3 nào không thể pin).
- **Rollback:** Lệnh kubectl để tắt Kyverno Enforce thành Audit nếu bị chặn nhầm.
- **Sign-off:** Tạo các checkbox [ ] để bạn, CDO02 và Mentor ký tên (đánh dấu x).
