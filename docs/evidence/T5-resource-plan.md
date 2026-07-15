# Báo cáo Cấu hình Resource Requests/Limits (Task T5)

## 1. Đánh giá Tình trạng (Diagnostics)

Sau khi kiểm tra số liệu thực tế bằng lệnh `kubectl -n techx-tf3 top pods` và đối chiếu với cấu hình `values-prod.yaml` hiện hành (từ nhánh `main`), hệ thống ghi nhận các vấn đề resource sau:
- **Lỗi OOMKilled:** 
  - `jaeger` từng bị OOMKilled (Exit Code 137) giữa lúc load test 200 user (giới hạn cũ 1Gi chưa đủ).
- **Nguy cơ chạm ngưỡng Limit:**
  - `prometheus` và `opensearch` đã chạm ngưỡng >80% limit ngay cả khi tải thấp.
  - `kafka` limit 1Gi vẫn chưa đủ dư dả, nguy cơ OOM.
  - `payment` đã dùng ~50-54% limit (180Mi) chỉ với 10 user nền, dễ gây thắt cổ chai khi tính tiền.
  - `shipping` (20Mi) và `quote` (40Mi) có limit quá mỏng cho tải 200 user, không có HPA bù tải.
- **Lỗi QoS BestEffort:** 
  - Ứng dụng `llm` và một số dịch vụ khác rơi vào nhóm nguy hiểm **QoS BestEffort** do thiếu cấu hình requests/limits rõ ràng.

---

## 2. Bảng Đề xuất Cấu hình MỚI (Memory)

> **Quan trọng — request và limit trả lời 2 câu hỏi khác nhau, đừng gộp chung:**
> - **`requests` (CPU/Memory):** Scheduler dùng để quyết định đặt pod lên node nào (tổng request phải ≤ allocatable của node). Đây là mức "đặt cọc chắc chắn có".
> - **`limits` (CPU/Memory):** Trần cứng giới hạn không cho vượt qua. Tổng limits của các pod trên một node **được phép** vượt quá sức chứa thật của node (overcommit). Điều này giúp tối ưu tài nguyên, vì không phải lúc nào tất cả các pod cũng đồng loạt dùng tới đỉnh limit. Việc đặt `requests` thấp hơn `limits` là có chủ đích (Burstable QoS), cho phép hệ thống linh hoạt hơn thay vì cứng nhắc chiếm chỗ (Guaranteed QoS).

### Bảng Thông số (Đáp ứng DoD)

Dưới đây là các thông số thực tế đã được chốt và áp dụng vào cấu hình `values-prod.yaml`:

| Tên Service | RAM Requests | RAM Limits | Lý do thay đổi (Theo số liệu thực tế & Mandate #2) |
| :--- | :--- | :--- | :--- |
| **grafana** (main+sidecar) | `608Mi` | `1280Mi` | Tăng cao làm vùng đệm an toàn, xử lý triệt để lỗi OOMKilled. |
| **jaeger** | `750Mi` | `2Gi` | **OOMKilled thật** (Exit Code 137) giữa lúc load test 200 user. Tăng limit tương tự nhóm quan sát. |
| **prometheus** | `450Mi` | `1200Mi` | Đã ở mức >80% limit ngay cả khi tải thấp. |
| **opensearch** | `750Mi` | `1600Mi` | Tương tự Prometheus, ngốn nhiều RAM khi tải tăng. |
| **opentelemetry-collector**| *(default)* | `350Mi` | Tự thêm giới hạn — collector ăn theo volume trace tăng. |
| **kafka** | `650Mi` | `1.5Gi` | Tăng thêm lần 2 sau khi mốc 1Gi vẫn chưa đủ dư dả. |
| **payment** | `100Mi` | `300Mi` | Đã dùng ~50-54% limit chỉ với 10 user nền — đứng đường charge tiền, ưu tiên cao nhất tránh OOM lúc checkout. |
| **shipping** | `8Mi` | `64Mi` | Quá mỏng (limit cũ 20Mi), không có HPA bù tải nếu chạm mốc. |
| **quote** | `24Mi` | `80Mi` | Quá mỏng (limit cũ 40Mi), shipping phụ thuộc quote. |
| **product-catalog** | `32Mi` | `64Mi` | Backend traffic cao, có lịch sử crash (REL-14). Nâng giới hạn an toàn. |
| **checkout** | `32Mi` | `64Mi` | Dịch vụ trọng yếu, cấu hình cân bằng Burstable QoS. |
| **cart** | `64Mi` | `160Mi` | Cấu hình giới hạn an toàn. |
| **frontend** | `100Mi` | `250Mi` | Chịu lượng lớn traffic HTTP từ web khách. |
| **frontend-proxy**| `32Mi` | `65Mi` | Cổng vào duy nhất (Envoy), thiết lập nhẹ nhàng, dư dả. |
| **llm** | `96Mi` | `256Mi` | Bổ sung tường minh để thoát khỏi QoS BestEffort nguy hiểm. |
| **postgresql** | `256Mi` | `512Mi` | Datastore quan trọng, đảm bảo không bị OOM. |
| **valkey-cart** | `32Mi` | `128Mi` | Datastore tạm, thiết lập đủ dùng. |
| *(Các app còn lại)* | *Tuỳ biến* | *Tuỳ biến*| Đồng bộ hoá để tối ưu hệ thống, tách biệt rõ ràng requests và limits. |

---

## 3. Tiêu chí hoàn thành (DoD)
- [x] Không còn pod critical ở QoS BestEffort.
- [x] Có bảng request/limit theo service với lý do rõ ràng (Dựa trên số liệu thực tế được verify trên live cluster và Mandate #2).
- [x] Cập nhật thành công cấu hình vào `values-prod.yaml`.
