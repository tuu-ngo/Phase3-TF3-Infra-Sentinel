# AIE2 / Shopping Copilot - Priority Backlog (TF3 / Nhóm AI/AIE)

Tài liệu quản lý tiến độ và xếp hạng ưu tiên các hạng mục công việc của mảng AIE/Shopping Copilot cho Phase 3. Các hạng mục được xếp hạng ưu tiên theo công thức chuẩn:

$$\text{Priority Score} = \text{Probability} \times \text{Severity} \times \text{Business Impact}$$

Trong đó, mỗi tiêu chí được đánh giá theo thang điểm từ 1 đến 5:
- Probability (Khả năng xảy ra): 1 = Rất thấp, 5 = Rất cao.
- Severity (Mức nghiêm trọng): 1 = Rất thấp, 5 = Cực kỳ nghiêm trọng.
- Business Impact (Tác động Business): 1 = Rất thấp, 5 = Rất cao.

*Thang điểm Priority Score (1 - 125):*
- 75 - 125: Tối ưu tiên
- 40 - 74: Cao
- 20 - 39: Trung bình
- 1 - 19: Thấp

---

## 📋 Danh sách Backlog Ưu Tiên AIE

| Mã Task | Hạng mục công việc | Probability (1-5) | Severity (1-5) | Business Impact (1-5) | Priority Score | Mức ưu tiên | Tuần thực hiện |
|---|---|:---:|:---:|:---:|:---:|---|---|
| **AIE-03** | **Cổng bảo vệ Excessive-Agency & Confirmation Gate cho Giỏ hàng** | 4 | 5 | 5 | **100** / 125 | Tối ưu tiên | Tuần 1 |
| **AIE-01** | **Module gRPC Client tích hợp cho Shopping Copilot** | 4 | 4 | 4 | **64** / 125 | Cao | Tuần 1 |
| **AIE-02** | **Logic Định tuyến Intent & Cơ chế Tool-calling** | 4 | 4 | 4 | **64** / 125 | Cao | Tuần 2 |

---

## 🛠️ Chi tiết từng hạng mục công việc AIE

### 1) Task AIE-03: Cổng bảo vệ Excessive-Agency & Confirmation Gate cho Giỏ hàng
- **Mô tả**: Triển khai middleware/guardrail chặn hành vi AI tự ý thực hiện thao tác ghi dữ liệu như thêm vào giỏ, xóa giỏ, checkout hoặc các thao tác có rủi ro tài chính. Khi cần thực hiện hành động ghi, frontend sẽ hiển thị nút xác nhận và chỉ thực thi sau khi nhận token confirm hợp lệ.
- **Rủi ro**: Rất cao nếu không có guardrail; có thể gây hành vi không mong muốn hoặc thao tác sai trên hệ thống thật.
- **Tác động Business**: Bảo vệ luồng thanh toán và giỏ hàng — khu vực có ảnh hưởng trực tiếp tới doanh thu và trải nghiệm khách hàng.
- **Phạm vi thực hiện**:
  - Implement input filter / prompt injection guard
  - Implement confirmation gate bằng HMAC token
  - Chặn các action bị cấm tuyệt đối: EmptyCart, PlaceOrder, Charge
  - Kết nối với frontend để hiển thị UI confirmation
- **Điều kiện hoàn thành**:
  - AI không thể tự ý gọi action ghi không có xác nhận
  - Tất cả hành động ghi phải đi qua confirmation flow
  - Có test cho deny/pending/approve cases
- **Metrics đo lường**:
  - Blocked unsafe actions rate
  - Confirmation success rate
  - Security incident count (should be zero)
- **Trụ chấm điểm**: Security: cực cao, Reliability: cực cao, Customer Trust: cao

### 2) Task AIE-01: Module gRPC Client tích hợp cho Shopping Copilot
- **Mô tả**: Thiết kế và triển khai gRPC client kết nối trực tiếp tới các service nội bộ của TechX Corp, đặc biệt ProductCatalogService và CartService, để làm nền tảng cho các tool của agent.
- **Rủi ro**: Thấp đến trung bình; chủ yếu là lỗi kết nối, schema mismatch hoặc timeout.
- **Tác động Business**: Cho phép agent tương tác thật với hệ thống sản phẩm và giỏ hàng, thay vì dùng mockup.
- **Phạm vi thực hiện**:
  - Implement client stub cho ProductCatalogService
  - Implement client stub cho CartService
  - Xử lý retry / timeout / error mapping
  - Chuẩn hóa response để tool có thể dùng được
- **Điều kiện hoàn thành**:
  - Có thể gọi thành công các RPC core từ module Shopping Copilot
  - Có test integration cơ bản
  - Có log và error handling rõ ràng
- **Metrics đo lường**:
  - Connection success rate
  - RPC latency p95
  - Tool execution success rate
- **Trụ chấm điểm**: Security: trung bình, Reliability: cao, Customer Experience: cao

### 3) Task AIE-02: Logic Định tuyến Intent & Cơ chế Tool-calling
- **Mô tả**: Xây dựng engine xử lý intent cho Shopping Copilot bằng LLM hoặc prompt-based routing, cho phép agent phân tích câu hỏi khách hàng, trích xuất tham số và chọn tool phù hợp như SearchProducts, GetProductReviews, GetCart.
- **Rủi ro**: Trung bình; rủi ro chính là intent misclassification hoặc tool selection sai.
- **Tác động Business**: Tăng độ chính xác của trải nghiệm RAG và cải thiện tỷ lệ khách hàng tìm thấy sản phẩm phù hợp, từ đó tăng khả năng đưa vào giỏ hàng.
- **Phạm vi thực hiện**:
  - Xây dựng prompt/logic routing
  - Chọn tool đúng theo intent
  - Trích xuất tham số đầu vào
  - Bọc output sao cho có thể dùng tiếp cho câu trả lời grounded
- **Điều kiện hoàn thành**:
  - Đạt độ chính xác trên bộ test intent mẫu
  - Hỗ trợ ít nhất 3 intent core: tìm sản phẩm, hỏi review, xem giỏ hàng
  - Có fallback khi tool không rõ hoặc không tìm thấy kết quả
- **Metrics đo lường**:
  - Task-success Eval Rate
  - Intent accuracy
  - Tool-call success rate
- **Trụ chấm điểm**: Customer Experience: cao, Reliability: trung bình

---

## 📅 Đề xuất phân bổ theo tuần

- **Tuần 1**: AIE-03 + AIE-01 (bảo mật + nền tảng)
- **Tuần 2**: AIE-02 (logic routing và tool-calling)
- **Tuần 3**: Tuning, eval, observability và hardening

---

## 📝 Ghi chú cho Hội đồng duyệt

Các task này có giá trị chiến lược vì:
- Làm nền tảng cho shopping copilot chạy thực tế, không chỉ demo.
- Bảo vệ luồng ra tiền và giảm rủi ro vận hành.
- Tạo cơ sở để đo lường và đánh giá chất lượng agent bằng các metric thực tế.
- Phù hợp với mục tiêu Phase 3: nâng cao trải nghiệm khách hàng, bảo mật và độ tin cậy.