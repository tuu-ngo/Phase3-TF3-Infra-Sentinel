# T9 Image Supply Chain Evidence Report

**Status: PENDING RUNTIME VERIFICATION**

## 1. Executive Summary
Báo cáo này cung cấp bằng chứng kỹ thuật (evidence) xác nhận chuỗi cung ứng container image (Image Supply Chain) đã được kiểm soát chặt chẽ thông qua Immutable Digest Pinning và Trivy/Inspector Security Gates.

## 2. ECR Tag Immutability
- Tính năng **Tag Immutability** đã được bật trên ECR `techx-corp`.
- Không một image nào có thể bị ghi đè tag sau khi đã push thành công.
- Evidence: Pipeline được cấu hình kiểm tra idempotency. Các tag đã tồn tại sẽ bị `skip push` và sử dụng lại `digest` gốc, bảo vệ nguyên vẹn artifacts.

## 3. Immutable Digest Pinning
Tất cả ứng dụng nội bộ và sidecar/init containers đều được triển khai dựa trên SHA256 Digest:
- **Kafka**: Triển khai với digest `sha256:afc05edcd00b7f56c8331d5e4a83c7ff6bf46182fd0667033529c964bccc2e68`.
- **BusyBox (init-kafka-data & wait-for)**: Ghim cố định `1.36@sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662`. Loại bỏ hoàn toàn `busybox:latest`.

## 4. Trivy CI Security Gate
- **Tooling**: Sử dụng Trivy phiên bản cố định qua Github Action (`setup-trivy@81e514348e19b6112ce2a7e3ecbafe19c1e1f567` chạy binary `v0.72.0`).
- **Scanning Context**: Quét trực tiếp ECR URI kèm Digest (`techx-corp@sha256:...`) ngay sau khi push.
- **Architecture**: Quét độc lập trên mọi platform target (`linux/amd64`, `linux/arm64`).
- **Enforcement**: CI Pipeline sẽ chủ động fail `exit 1` nếu Json report trả về số lượng `HIGH` hoặc `CRITICAL` > 0.
- Evidence Artifacts: Các báo cáo JSON sẽ luôn được đính kèm vào phần Artifacts của Github Actions.
- Workflow Run ID: *[Pending Runtime Output]*

## 5. Amazon Inspector Findings Snapshot
*Bằng chứng này được trích xuất bằng script `t9-collect-image-evidence.sh` đối với các image đang chạy.*
- Inspector Result: *[Pending Runtime Output]*

## 6. Runtime kubernetes Validation
- Kiểm tra Pod tại Namespace `techx-tf3` sẽ xác nhận toàn bộ container và initContainer `imageID` đang map đúng với digest đã định nghĩa trong cấu hình Helm.
- Argo CD Revision: *[Pending Runtime Output]*
- Runtime Digest Matches: *[Pending Runtime Output]*
