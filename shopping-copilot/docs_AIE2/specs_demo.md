# Đặc tả Kỹ thuật: Shopping Copilot Agentic Assistant (TF3 - Phase 3)

> Phiên bản: 1.2.0 | Ngày: 2026-07-08 | Đội: AIO02 — TF3
>
> Tài liệu này là bản kỹ thuật chi tiết dành cho developer và engineer triển khai module Shopping Copilot. Nội dung bao gồm stack công nghệ, cấu trúc code, API contract, luồng xử lý, guardrail, cấu hình môi trường, kiểm thử và vận hành.

## 1. Mục tiêu triển khai

Shopping Copilot là module backend/agentic layer cho storefront TechX Corp. Mục tiêu của module là:

- Nhận input từ người dùng dưới dạng chat text.
- Gọi LLM để xác định intent và lựa chọn tool phù hợp.
- Gọi các service backend qua gRPC để đọc hoặc ghi dữ liệu.
- Trả lời khách hàng bằng câu trả lời grounded, an toàn và có kiểm soát.

### 1.1 Scope ban đầu

Phase đầu ưu tiên triển khai các chức năng core:
- Tìm sản phẩm bằng ngôn ngữ tự nhiên.
- Hỏi đáp grounded từ review thật.
- Xem giỏ hàng.
- Thêm item vào giỏ hàng với confirmation gate.

### 1.2 Ràng buộc kỹ thuật bắt buộc

- Không được phép hallucinate khi trả lời; chỉ dùng dữ liệu từ tool.
- Phải có multi-turn memory để hiểu ngữ cảnh hội thoại.
- Phải implement đầy đủ 3 lớp guardrail: input filter, confirmation gate, fallback/max iterations.
- Mọi tool invocation phải có audit log và tracing.
- Không được để exception không được xử lý làm crash service.

---

## 2. Stack công nghệ đề xuất

### 2.1 Backend runtime

- Python 3.11+
- FastAPI
- Pydantic
- Uvicorn / Gunicorn
- grpcio
- protobuf

### 2.2 AI / Agent layer

- LangChain hoặc tương đương
- Groq API (khuyến nghị cho phase đầu)
- python-dotenv

### 2.3 Security và observability

- HMAC-SHA256 cho confirmation token
- structlog hoặc logging chuẩn
- OpenTelemetry
- Jaeger

### 2.4 Testing

- pytest
- httpx / TestClient
- pytest-cov

---

## 3. Cấu trúc thư mục và trách nhiệm module

```text
shopping-copilot/
├── main.py                      # FastAPI entrypoint, route registration
├── agent/
│   ├── __init__.py
│   ├── copilot_agent.py         # ReAct orchestration loop
│   └── prompts.py               # system prompt và prompt templates
├── tools/
│   ├── __init__.py
│   ├── catalog_tool.py          # search_products_tool
│   ├── cart_tool.py             # add_to_cart_tool, get_cart_tool
│   ├── reviews_tool.py          # get_product_reviews_tool
│   ├── recommendation_tool.py  # optional
│   ├── currency_tool.py         # optional
│   └── shipping_tool.py         # optional
├── guardrails/
│   ├── __init__.py
│   ├── input_filter.py          # lớp 1: prompt injection filter
│   ├── confirmation.py         # lớp 2: confirmation gate
│   └── fallback.py              # lớp 3: fallback + max iterations
├── memory/
│   ├── session.json             # schema mẫu cho session memory
│   └── cache.json               # schema mẫu cho cache memory
├── protos/
│   ├── demo.proto
│   ├── demo_pb2.py
│   └── demo_pb2_grpc.py
├── demo_guardrails.py          # demo server cho guardrails
├── test_guardrails.py          # unit tests cho guardrails
└── test_tools.py               # tests cho tool wrappers
```

### 3.1 Vai trò thực thi từng module

- main.py
  - Khởi tạo FastAPI app
  - Đăng ký route /api/chat, /api/confirm, /health
  - Gắn middleware CORS, logging, tracing

- agent/copilot_agent.py
  - Tạo LLM client
  - Quản lý conversation context và session memory
  - Chạy ReAct loop
  - Thực hiện tool calling và đếm iterations
  - Ghi audit log

- agent/prompts.py
  - Định nghĩa system prompt, tool selection hints, confirmation message template

- tools/*
  - Mỗi tool phải expose một interface thống nhất: input dict -> output string
  - Tool wrapper nên bắt và chuyển lỗi gRPC thành lỗi nghiệp vụ rõ ràng

- guardrails/*
  - Input filter: chặn trước khi gọi LLM
  - Confirmation gate: chặn hành động ghi chưa được xác nhận
  - Fallback: bọc exception và trả response thân thiện

---

## 4. API contract chi tiết

### 4.1 POST /api/chat

Request body:

```json
{
  "user_id": "user-001",
  "session_id": "optional-session-id",
  "message": "Tìm tai nghe dưới 50 đô"
}
```

Response thành công:

```json
{
  "status": "ok",
  "message": "Tôi tìm thấy một số sản phẩm phù hợp",
  "data": {
    "intent": "tim_san_pham",
    "tool_used": "search_products_tool",
    "requires_confirmation": false
  }
}
```

Response pending confirmation:

```json
{
  "status": "pending_confirmation",
  "message": "Vui lòng xác nhận hành động thêm sản phẩm vào giỏ",
  "data": {
    "action": "AddItem",
    "token": "base64url.payload.signature"
  }
}
```

Response lỗi:

```json
{
  "status": "error",
  "message": "Yêu cầu bị từ chối vì lý do bảo mật",
  "error_code": "INPUT_BLOCKED"
}
```

### 4.2 POST /api/confirm

Request body:

```json
{
  "user_id": "user-001",
  "token": "<confirmation-token>"
}
```

Response:

```json
{
  "status": "ok",
  "message": "Đã thêm sản phẩm vào giỏ hàng",
  "data": {
    "action": "AddItem",
    "executed": true
  }
}
```

### 4.3 GET /health

Response:

```json
{
  "status": "ok"
}
```

---

## 5. Luồng xử lý trong code

### 5.1 Flow chính

1. Nhận request từ frontend.
2. Kiểm tra input qua input filter.
3. Nếu input không an toàn => trả lỗi ngay.
4. Load session memory cho user/session.
5. Gửi message + context + tool schemas tới LLM.
6. Nếu LLM chọn tool đọc => thực thi tool và trả kết quả về LLM.
7. Nếu LLM chọn tool ghi => gọi confirmation gate.
8. Nếu cần xác nhận => trả pending confirmation.
9. Nếu user xác nhận => thực thi hành động thật qua gRPC.
10. Ghi audit log và cập nhật session memory.

### 5.2 Pseudocode triển khai

```python
@app.post("/api/chat")
def chat(request: ChatRequest):
    result = check_input(request.message)
    if not result.is_safe:
        return error_response("INPUT_BLOCKED", result.blocked_reason)

    session = load_or_create_session(request.user_id, request.session_id)
    response = agent.process(request.message, session)
    return response
```

### 5.3 Quy trình xử lý tool call

- Tool chỉ được gọi khi LLM quyết định rõ intent.
- Mỗi tool call phải ghi log:
  - tool_name
  - params
  - result
  - latency_ms
  - iteration
  - timestamp

---

## 6. Ánh xạ intent → tool → gRPC

### 6.1 Bảng mapping chính

| Intent | Tool | Service | Method |
|---|---|---|---|
| Tìm sản phẩm | search_products_tool | ProductCatalogService | SearchProducts |
| Hỏi review | get_product_reviews_tool | ProductReviewService | GetProductReviews |
| Thêm vào giỏ | add_to_cart_tool | CartService | AddItem |
| Xem giỏ | get_cart_tool | CartService | GetCart |
| So sánh sản phẩm | search_products_tool + get_product_reviews_tool | ProductCatalogService + ProductReviewService | SearchProducts + GetProductReviews |
| Gợi ý | get_recommendations_tool | RecommendationService | TBD |
| Quy đổi tiền | convert_currency_tool | CurrencyService | TBD |
| Tính phí ship | get_shipping_quote_tool | ShippingQuotationService | TBD |

### 6.2 Contract tool wrapper

Mỗi tool nên có cấu trúc như sau:

```python
class ToolSpec:
    name: str
    description: str
    input_schema: dict
    handler: Callable
```

Ví dụ:

```python
def search_products_tool(query: str) -> str:
    request = SearchProductsRequest(query=query)
    response = catalog_stub.SearchProducts(request)
    return serialize_search_results(response.results)
```

---

## 7. Guardrail implementation detail

### 7.1 Input Filter

- Dùng regex matching trên raw message trước khi gửi tới LLM.
- Nếu match pattern tấn công, trả về blocked response ngay.
- Không gọi LLM khi blocked.
- Log type của attack để audit.

### 7.2 Confirmation Gate

- Hành động ghi được phân loại thành 3 nhóm:
  - DENIED_ACTIONS: EmptyCart, PlaceOrder, Charge
  - CONFIRM_REQUIRED_ACTIONS: AddItem
  - READ_ACTIONS: GetCart, SearchProducts, GetProductReviews

- Confirmation token format:
  - base64url(payload) + "." + HMAC-SHA256(payload)
- Payload chứa:
  - user_id
  - action
  - params
  - exp

- Frontend phải gửi token lại qua /api/confirm để thực thi hành động thật.

### 7.3 Fallback và Max Iterations

- max_iterations = 3
- Nếu LLM gọi tool quá 3 lần liên tiếp mà vẫn không trả câu trả lời cuối cùng => raise MaxIterationsExceeded
- Bọc exception bằng decorator with_fallback
- Trả về response thân thiện và log đầy đủ

---

## 8. Memory và cache design

### 8.1 Session memory

Session memory phục vụ multi-turn experience. Mỗi session cần lưu:
- user_id
- session_id
- created_at
- last_active
- messages
- pending_confirmation
- metadata.total_turns
- metadata.total_tool_calls
- metadata.last_intent

### 8.2 Cache memory

Cache nên dùng cho các tool read-heavy để giảm latency và traffic. Quy tắc:
- Cache được phép: search, reviews, recommendations, currency
- Không cache: add_to_cart, get_cart, shipping estimate

Cache key nên gồm:
- tool_name
- hash(params)

### 8.3 Production note

Trong EKS production, nên migrate session/cache từ in-memory sang Valkey hoặc Redis-compatible store để hỗ trợ multi-replica.

---

## 9. Logging, tracing và audit

### 9.1 Structured logging

Log các event sau:
- request_received
- input_blocked
- llm_call_started
- tool_called
- confirmation_requested
- confirmation_verified
- tool_execution_failed
- fallback_triggered

### 9.2 OpenTelemetry

- Tạo span cho mỗi request
- Tạo span riêng cho mỗi tool call
- Gắn attribute: user_id, session_id, tool_name, action, status

### 9.3 Audit log schema

```json
{
  "timestamp": "2026-07-08T10:00:00Z",
  "user_id": "user-001",
  "session_id": "sess-123",
  "tool_name": "add_to_cart_tool",
  "action": "AddItem",
  "params": {"product_id": "P1", "quantity": 2},
  "result": "success",
  "latency_ms": 120,
  "iteration": 1
}
```

---

## 10. Cấu hình môi trường

Các biến môi trường cần có:

```text
GROQ_API_KEY=
GROQ_MODEL=llama-3.1-8b-instant
COPILOT_CONFIRMATION_SECRET=change-me-in-prod
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
LOG_LEVEL=INFO
```

### 10.1 Khuyến nghị production

- Không hardcode secret vào source
- Dùng Kubernetes Secret hoặc Secret Manager
- Không để fallback secret dùng trong production

---

## 11. Testing strategy

### 11.1 Unit test

- Input filter: safe / unsafe input
- Confirmation gate: approve / pending / denied
- Fallback: max iterations, gRPC error, unknown error

### 11.2 Integration test

- Test /api/chat với mock hoặc stub gRPC
- Test /api/confirm với token hợp lệ và token hết hạn
- Test logging và response contract

### 11.3 Acceptance test

- Người dùng hỏi tìm sản phẩm => trả kết quả đúng
- Người dùng yêu cầu thêm vào giỏ => trả pending confirm
- Người dùng xác nhận => hành động được thực thi
- Prompt injection bị chặn

---

## 12. Deployment và vận hành

### 12.1 Local run

```bash
cd shopping-copilot
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 12.2 Containerization

- Container image nên chạy non-root user
- Health check endpoint phải trả 200 khi service ổn định
- Cấu hình resource request/limit rõ ràng

### 12.3 Kubernetes / EKS

- Dùng Secret cho API keys và confirmation secret
- Expose service qua ingress hoặc internal service
- Enable tracing tới Jaeger
- Giữ session/cache state externalized nếu scale > 1 replica

---

## 13. Các điểm cần chú ý khi implement

- Tool wrapper phải tách biệt khỏi prompt logic để dễ test
- Không nên để LLM trực tiếp quyết định hành động ghi mà không qua confirmation gate
- Phải chuẩn hóa output từ tool về dạng string hoặc structured JSON để LLM dễ dùng
- Khi gRPC service unavailable, phải trả response thân thiện ngay thay vì để request treo
- Nên có timeout cho LLM và gRPC call để bảo vệ SLO

---

## 14. Tiêu chí hoàn thành cho developer

Module được xem là triển khai xong khi:

- Có thể chạy local và expose các endpoint chuẩn
- Chat request có thể xử lý intent tìm sản phẩm và review
- AddItem yêu cầu confirmation trước khi gọi gRPC thật
- Input filter chặn prompt injection đúng
- Fallback trả response thân thiện khi lỗi xảy ra
- Audit log và tracing có sẵn
- Unit/integration tests chạy xanh