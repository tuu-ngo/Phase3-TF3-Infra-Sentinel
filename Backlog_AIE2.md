### ĐỒNG GÓP DANH MỤC BACKLOG - NHÓM AI (HƯỚNG AIE)

Dưới đây là các đầu việc chi tiết tầng AI cần triển khai trong các tuần tiếp theo, được đánh giá dựa trên Ma trận Rủi ro × Tác động Business để Hội đồng duyệt chi phí và hạ tầng:

#### 1. Task AIE-01: Xây dựng Module gRPC Client tích hợp cho Shopping Copilot
* **Mô tả:** Lập trình mã nguồn thiết lập gRPC Client kết nối trực tiếp sang các Endpoint nội bộ của `ProductCatalogService` và `CartService` do các bạn CDO quản lý để sẵn sàng làm công cụ (Tools) cho Agent gọi.
* **Mức độ ưu tiên:** Cao (Ưu tiên 1) - Vì đây là nền tảng cốt lõi để tính năng Agent có thể chạy thật (không dùng mockup).
* **Tác động Business:** Giúp kết nối tính năng chat trực tiếp với luồng sản phẩm ra tiền của hệ thống.
* **Rủi ro hạ tầng:** Thấp, không tốn thêm tài nguyên EC2, nằm hoàn toàn trong trần ngân sách.

#### 2. Task AIE-02: Lập trình Logic Định tuyến Intent và Cơ chế Tool-calling
* **Mô tả:** Xây dựng bộ não xử lý cho Shopping Copilot dựa trên framework LLM (như LangChain/LlamaIndex hoặc tự cấu trúc prompt). Lập trình để LLM phân tích câu hỏi của khách hàng, tự động trích xuất tham số và đưa ra quyết định chọn Tool (`SearchProducts` hoặc `GetProductReviews`) một cách chính xác.
* **Mức độ ưu tiên:** Cao (Ưu tiên 2).
* **Tác động Business:** Đảm bảo trải nghiệm RAG chính xác (grounded), giải quyết bài toán khách hàng tìm sản phẩm tự nhiên, trực tiếp thúc đẩy tỷ lệ bỏ sản phẩm vào giỏ.
* **Đo lường (Metrics):** Đo lường và kiểm chứng bằng tỷ lệ chạy Task thành công (Task-success Eval Rate).

#### 3. Task AIE-03: Triển khai Cổng bảo vệ Excessive-Agency và Confirmation Gate cho Giỏ hàng
* **Mô tả:** Viết code xử lý bọc lót (Middleware) chặn đứng hành vi tự ý ghi dữ liệu của AI. Phối hợp với Frontend hiển thị nút "Xác nhận hành động" mỗi khi khách yêu cầu thêm sản phẩm vào giỏ hàng. Chặn tuyệt đối không cho AI tự ý gọi API checkout hoặc xóa giỏ hàng khi chưa có lệnh.
* **Mức độ ưu tiên:** Tối khẩn cấp (Ưu tiên 1 - Bảo vệ an toàn).
* **Tác động Business:** Bảo vệ luồng ra tiền quan trọng nhất hệ thống (Checkout). Đảm bảo hệ thống không bị phá hoại hoặc đặt đơn hàng giả lập khi có xung đột hành vi từ AI.
* **Trụ chấm điểm:** Đóng góp trực tiếp vào trụ **Security** và **Reliability** của toàn TF3.