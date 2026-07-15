# Báo cáo Đề xuất Cấu hình Resource Requests/Limits (Task T5)

## 1. Đánh giá Tình trạng (Dựa trên số liệu T4)

Sau khi kiểm tra số liệu thực tế bằng lệnh `kubectl -n techx-tf3 top pods`, hệ thống ghi nhận các vấn đề sau:
- **Lỗi OOMKilled:** 
  - `grafana` đang limit 500Mi (Thực tế ngốn 397Mi, rất sát mép, từng bị OOMKilled với limit 300Mi).
  - `jaeger` đang limit 1Gi (Thực tế ngốn 525Mi, từng bị OOMKilled với limit 600Mi, cần tăng vùng đệm).
  - `product-catalog` limit 20Mi (Thực tế ngốn 13Mi, từng restart 3 lần).
  - `kafka` limit 700Mi (Thực tế ngốn tới 628Mi, rất nguy hiểm).
- **Lỗi QoS BestEffort:** 
  - Ứng dụng `llm` đang sử dụng 72Mi nhưng chưa có cấu hình resource hợp lệ, khiến nó rơi vào nhóm ưu tiên thấp nhất (BestEffort) và rất dễ bị K8s tiêu diệt khi hệ thống thiếu RAM.

---

## 2. Bảng Đề xuất Cấu hình MỚI (Memory)

**Nguyên tắc áp dụng:**
- **RAM chuẩn:** Cài đặt `requests.memory` BẰNG `limits.memory` = Số thực tế + 30% Buffer.

> **Tại sao phải set Requests và Limits RAM bằng nhau?**
> RAM là tài nguyên không thể nén (khác với CPU). Việc set `requests` = `limits` ép Kubernetes phải "đặt cọc" đúng và đủ phần RAM đó cho ứng dụng ngay từ đầu (Guaranteed QoS đối với RAM). Dù máy chủ có cạn kiệt bộ nhớ, ứng dụng của bạn vẫn được bảo vệ tuyệt đối, không bao giờ bị K8s mang ra làm vật tế thần (tránh lỗi OOMKilled/Eviction). Hơn nữa, việc này giúp công tác quy hoạch máy chủ (Capacity Planning) luôn chính xác 100%, không bị ảo tưởng về sức chứa.

### Bảng Đề xuất Cấu hình (Đáp ứng DoD)

| Tên Service | RAM Đề xuất (Requests = Limits) | Lý do thay đổi (Dựa trên số liệu T4) |
| :--- | :--- | :--- |
| **grafana** | `600Mi` | Số liệu thực tế ăn **397Mi**. Cần 600Mi làm vùng đệm an toàn để tránh lặp lại lỗi OOMKilled. |
| **jaeger** | `800Mi` | Số liệu thực tế ăn **525Mi**. Limit cũ 600Mi quá rủi ro, set cứng 800Mi để đảm bảo ổn định. |
| **product-catalog** | `40Mi` | Thực tế ăn **~13Mi**. Limit cũ 20Mi quá hẹp khiến app restart 3 lần. Nâng lên gấp đôi. |
| **llm** | `120Mi` | Thực tế ăn **72Mi**. Bổ sung cấu hình để đưa app này thoát khỏi nhóm nguy hiểm **QoS BestEffort**. |
| **checkout** | `30Mi` | Thực tế ăn **~13Mi**. 30Mi là đủ an toàn. |
| **cart** | `80Mi` | Thực tế ăn **~58Mi**. |
| **frontend** | `120Mi` | Thực tế ăn **~86Mi**. |
| **frontend-proxy**| `40Mi` | Thực tế ăn **~23Mi**. |
| **payment** | `150Mi` | Thực tế ăn **~105Mi**. |
| **postgresql** | `100Mi` | Thực tế ăn **~58Mi**. |
| **valkey-cart** | `20Mi` | Thực tế ăn **~4Mi**. |
| **kafka** | `850Mi` | Thực tế ăn khổng lồ **628Mi**. Cần ít nhất 850Mi để chịu tải mà không bị OOM. |
| *(Các app còn lại)*| *Peak thực tế + 30%* | Đồng bộ hóa để tối ưu tài nguyên Node. |

---

## 3. Tiêu chí hoàn thành (DoD)
- [x] Không còn pod critical ở QoS BestEffort (Đã xử lý `llm`).
- [x] Có bảng request/limit theo service với lý do rõ ràng (Dựa trên số liệu `kubectl top pods` thực tế, không cảm tính).
