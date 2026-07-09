### ĐỒNG GÓP DANH MỤC BACKLOG - NHÓM AI (HƯỚNG AIE)

Dưới đây là danh mục backlog chi tiết cho nhóm AI/AIE trong Phase 3, được rà soát theo góc nhìn ưu tiên kinh doanh, rủi ro vận hành và ảnh hưởng đến trụ Security/Reliability. Mỗi task được bổ sung thông tin về mục tiêu, phạm vi, điểm số ưu tiên, điều kiện hoàn thành và chỉ số đo lường.

---

## 1. Cách tính điểm ưu tiên

Mỗi task được chấm theo thang điểm 1–5 cho 4 tiêu chí:

- Tác động Business (Business Impact)
- Rủi ro bảo mật / vận hành (Risk)
- Khả năng hoàn thành trong thời gian ngắn (Speed / Feasibility)
- Giá trị nền tảng / mở đường cho các task sau (Foundation Value)

Công thức gợi ý:

- Priority Score = Business Impact + Risk + Foundation Value + Feasibility
- Điểm càng cao => ưu tiên càng cao

Kết quả phân loại:
- 16–20: Tối ưu tiên
- 12–15: Cao
- 8–11: Trung bình
- 4–7: Thấp

---

## 2. Backlog tasks

### 1) Task AIE-01: Xây dựng Module gRPC Client tích hợp cho Shopping Copilot
- **Mô tả:** Thiết kế và triển khai gRPC client kết nối trực tiếp tới các service nội bộ của TechX Corp, đặc biệt ProductCatalogService và CartService, để làm nền tảng cho các tool của agent.
- **Mức độ ưu tiên:** Cao
- **Priority Score:** 17/20
- **Tác động Business:** Cho phép agent tương tác thật với hệ thống sản phẩm và giỏ hàng, thay vì dùng mockup.
- **Rủi ro:** Thấp đến trung bình; chủ yếu là lỗi kết nối, schema mismatch hoặc timeout.
- **Phạm vi:**
  - Implement client stub cho ProductCatalogService
  - Implement client stub cho CartService
  - Xử lý retry / timeout / error mapping
  - Chuẩn hóa response để tool có thể dùng được
- **Điều kiện hoàn thành:**
  - Có thể gọi thành công các RPC core từ module Shopping Copilot
  - Có test integration cơ bản
  - Có log và error handling rõ ràng
- **Metrics:**
  - Connection success rate
  - RPC latency p95
  - Tool execution success rate
- **Trụ chấm điểm:** Security: trung bình, Reliability: cao, Customer Experience: cao

### 2) Task AIE-02: Lập trình Logic Định tuyến Intent và Cơ chế Tool-calling
- **Mô tả:** Xây dựng engine xử lý intent cho Shopping Copilot bằng LLM hoặc prompt-based routing, cho phép agent phân tích câu hỏi khách hàng, trích xuất tham số và chọn tool phù hợp như SearchProducts, GetProductReviews, GetCart.
- **Mức độ ưu tiên:** Cao
- **Priority Score:** 16/20
- **Tác động Business:** Tăng độ chính xác của trải nghiệm RAG và cải thiện tỷ lệ khách hàng tìm thấy sản phẩm phù hợp, từ đó tăng khả năng đưa vào giỏ hàng.
- **Rủi ro:** Trung bình; rủi ro chính là intent misclassification hoặc tool selection sai.
- **Phạm vi:**
  - Xây dựng prompt/logic routing
  - Chọn tool đúng theo intent
  - Trích xuất tham số đầu vào
  - Bọc output sao cho có thể dùng tiếp cho câu trả lời grounded
- **Điều kiện hoàn thành:**
  - Đạt độ chính xác trên bộ test intent mẫu
  - Hỗ trợ ít nhất 3 intent core: tìm sản phẩm, hỏi review, xem giỏ hàng
  - Có fallback khi tool không rõ hoặc không tìm thấy kết quả
- **Metrics:**
  - Task-success Eval Rate
  - Intent accuracy
  - Tool-call success rate
- **Trụ chấm điểm:** Customer Experience: cao, Reliability: trung bình

### 3) Task AIE-03: Triển khai Cổng bảo vệ Excessive-Agency và Confirmation Gate cho Giỏ hàng
- **Mô tả:** Triển khai middleware/guardrail chặn hành vi AI tự ý thực hiện thao tác ghi dữ liệu như thêm vào giỏ, xóa giỏ, checkout, hoặc các thao tác có rủi ro tài chính. Khi cần thực hiện hành động ghi, frontend sẽ hiển thị nút xác nhận và chỉ thực thi sau khi nhận token confirm hợp lệ.
- **Mức độ ưu tiên:** Tối khẩn cấp
- **Priority Score:** 20/20
- **Tác động Business:** Bảo vệ luồng thanh toán và giỏ hàng — khu vực có ảnh hưởng trực tiếp tới doanh thu và trải nghiệm khách hàng.
- **Rủi ro:** Rất cao nếu không có guardrail; có thể gây hành vi không mong muốn hoặc thao tác sai trên hệ thống thật.
- **Phạm vi:**
  - Implement input filter / prompt injection guard
  - Implement confirmation gate bằng HMAC token
  - Chặn các action bị cấm tuyệt đối: EmptyCart, PlaceOrder, Charge
  - Kết nối với frontend để hiển thị UI confirmation
- **Điều kiện hoàn thành:**
  - AI không thể tự ý gọi action ghi không có xác nhận
  - Tất cả hành động ghi phải đi qua confirmation flow
  - Có test cho deny/pending/approve cases
- **Metrics:**
  - Blocked unsafe actions rate
  - Confirmation success rate
  - Security incident count (should be zero)
- **Trụ chấm điểm:** Security: cực cao, Reliability: cực cao, Customer Trust: cao

---

## 3. Đề xuất phân bổ theo tuần

- **Tuần 1:** AIE-01 + AIE-03 (nền tảng + bảo mật)
- **Tuần 2:** AIE-02 (logic routing và tool-calling)
- **Tuần 3:** Tuning, eval, observability và hardening

---

## 4. Ghi chú cho Hội đồng duyệt

Các task này có giá trị chiến lược vì:
- Làm nền tảng cho shopping copilot chạy thực tế, không chỉ demo.
- Bảo vệ luồng ra tiền và giảm rủi ro vận hành.
- Tạo cơ sở để đo lường và đánh giá chất lượng agent bằng các metric thực tế.
- Phù hợp với mục tiêu Phase 3: nâng cao trải nghiệm khách hàng, bảo mật và độ tin cậy.