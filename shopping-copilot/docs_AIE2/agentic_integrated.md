# Tài liệu Tích hợp: Shopping Copilot → TechX Corp Platform

> **Phiên bản:** 1.0 | **Ngày:** 2026-07-09 | **Tác giả:** Team AI (AIO02 — TF3)  
> **Đối tượng đọc:** Team Dev (CDO01/CDO02) — chuẩn bị trước khi bàn giao chính thức.

---

## Mục lục

1. [Phần 1 — Verify: Trạng thái hiện tại của module so với hệ thống](#phần-1--verify-trạng-thái-hiện-tại-của-module-so-với-hệ-thống)  
2. [Phần 2 — Integration Plan: Tích hợp vào hệ thống & đề xuất Infra](#phần-2--integration-plan-tích-hợp-vào-hệ-thống--đề-xuất-infra)

---

## Phần 1 — Verify: Trạng thái hiện tại của module so với hệ thống

### 1.1 Tổng quan module hiện có

Module `shopping-copilot/` (nằm trong `Phase3-TF3-Infra-Sentinel/shopping-copilot/`) là một **FastAPI service** độc lập, triển khai ReAct tool-calling loop sử dụng Groq API (LangChain). Service phơi ra 3 HTTP endpoint:

| Endpoint | Method | Mục đích |
|---|---|---|
| `/api/chat` | POST | Gửi tin nhắn, nhận reply từ agent |
| `/api/confirm` | POST | Xác nhận hành động ghi (sau khi user bấm nút) |
| `/health` | GET | Health check |

### 1.2 Kiểm tra các thành phần đã có ✅

| Thành phần | File | Trạng thái | Ghi chú |
|---|---|---|---|
| **Entry point FastAPI** | `main.py` | ✅ Hoàn chỉnh | CORS wildcard, lazy-init agent, Pydantic models |
| **Agent orchestrator** | `agent/copilot_agent.py` | ✅ Hoàn chỉnh | ReAct loop, sliding window memory, audit log, `@with_fallback` |
| **System prompt** | `agent/prompts.py` | ✅ Hoàn chỉnh | Tiếng Việt, grounded, anti-hallucinate |
| **Tool: tìm sản phẩm** | `tools/catalog_tool.py` | ✅ Có | gRPC → `ProductCatalogService.SearchProducts` |
| **Tool: review sản phẩm** | `tools/review_tool.py` | ✅ Có | gRPC → `ProductReviewService.GetProductReviews` |
| **Tool: thêm vào giỏ** | `tools/cart_tool.py` | ✅ Có | gRPC → `CartService.AddItem` + Confirmation Gate |
| **Guardrail Lớp 1** | `guardrails/confirmation.py` | ✅ Hoàn chỉnh | HMAC-SHA256 stateless token, DENIED/CONFIRM/APPROVED |
| **Guardrail Lớp 2** | `guardrails/input_filter.py` | ✅ Hoàn chỉnh | 5 danh mục tấn công, regex pattern matching |
| **Guardrail Lớp 3** | `guardrails/fallback.py` | ✅ Hoàn chỉnh | Max 3 iterations, 7 loại exception → friendly message |
| **Session memory** | `memory/store.py` (SessionStore) | ✅ Hoàn chỉnh | In-memory dict, sliding window 20 msg, TTL 30 phút |
| **Tool result cache** | `memory/store.py` (CacheStore) | ✅ Hoàn chỉnh | LRU+TTL, 500 entries max |
| **Proto stubs** | `protos/demo_pb2*.py` | ✅ Compile sẵn | Từ `demo.proto` của TechX Corp |
| **Unit tests guardrails** | `test_guardrails.py` | ✅ Có | Bao phủ edge case HMAC, injection, fallback |
| **Demo server** | `demo_guardrails.py` | ✅ Có | FastAPI port 9000, không cần LLM hay gRPC |
| **Dependencies** | `requirements.txt` | ✅ Có | OTel đang bị comment out — cần bật |

### 1.3 Những gì còn thiếu — GAP Analysis ❌

#### GAP 1: Tools mở rộng chưa được implement

Theo `agentic_design.md` (Intent 4–6), các tools sau **chưa tồn tại** trong codebase và `tools/__init__.py` chỉ đang export 3 tools:

| Tool | File cần tạo | gRPC target | Mức độ |
|---|---|---|---|
| `get_cart_tool` | thêm vào `tools/cart_tool.py` | `CartService.GetCart` | **Core** (Intent 3b) |
| `get_recommendations_tool` | `tools/recommendation_tool.py` | `RecommendationService.ListRecommendations` | Mở rộng |
| `convert_currency_tool` | `tools/currency_tool.py` | `CurrencyService.Convert` | Mở rộng |
| `get_shipping_quote_tool` | `tools/shipping_tool.py` | `ShippingService.GetQuote` | Mở rộng |

> **Lưu ý:** `get_cart_tool` là **Core** — Intent 3 yêu cầu agent phải đọc được giỏ hàng hiện tại. Thiếu tool này = agent trả lời sai khi user hỏi _"giỏ hàng của tôi đang có gì?"_.

#### GAP 2: gRPC address bị hardcode về `localhost` — không dùng được trên EKS

Tất cả tools hiện tại dùng `localhost:<port>` sẽ thất bại ngay khi deploy lên Kubernetes vì các service chạy với DNS nội bộ cluster:

| Tool | Địa chỉ hiện tại | Địa chỉ đúng trên EKS |
|---|---|---|
| `catalog_tool.py` | `localhost:3550` | `product-catalog:3550` |
| `review_tool.py` | `localhost:3551` | `product-reviews:9090` ⚠️ |
| `cart_tool.py` | `localhost:7070` | `cart:7070` |

> **Bug nghiêm trọng:** `review_tool.py` dùng port `3551` nhưng theo `ARCHITECTURE.md`, `product-reviews` expose port `9090`. **Port này sai** — phải sửa trước khi tích hợp, mọi gRPC call đến reviews đều sẽ fail.

#### GAP 3: OpenTelemetry chưa được bật — không có observability

`requirements.txt` đang **comment out** toàn bộ OTel packages:

```
# opentelemetry-api>=1.20
# opentelemetry-sdk>=1.20
# opentelemetry-instrumentation-fastapi>=0.41b0
```

Và `copilot_agent.py` không có span instrumentation. Điều này có nghĩa:
- Không có span nào trong Jaeger cho shopping-copilot
- Không quan sát được latency LLM call / gRPC call từ agent
- Không thỏa mãn yêu cầu audit log mọi lời gọi tool ở dạng trace

#### GAP 4: Session memory chưa được persist — mất khi pod restart

`SessionStore` và `CacheStore` đang lưu hoàn toàn **in-memory** (Python dict). Khi pod bị restart (OOM, node drain, rolling update), toàn bộ session bị mất:
- User đang trong lúc `pending_confirmation` → bị mất token → phải làm lại
- Cache bị xóa → burst gRPC call sau restart

`agentic_design.md` mục 3 đã ghi chú: _"Trên EKS production, nên migrate sang Valkey instance đang có trong cluster"_ — đây là việc cần hoàn thành trước go-live.

#### GAP 5: Chưa có Dockerfile và không có entry trong Helm chart

Module `shopping-copilot/` **không có Dockerfile** và **không có entry nào** trong `techx-corp-chart/values.yaml`. Không thể build image, không thể deploy qua Helm.

#### GAP 6: CORS wildcard không phù hợp production

`main.py` cấu hình `allow_origins=["*"]` — cần restrict về domain frontend cụ thể trước khi bàn giao.

#### GAP 7: `cart_tool.py` dùng cơ chế confirmation gate cũ — double-check logic

`cart_tool.py` gọi `trigger_confirmation_gate()` bên trong tool function, trong khi `copilot_agent.py` đã bắt tên tool `"add_to_cart_tool"` ở layer `_react_loop` để gọi `request_confirmation()`. Điều này gây **double-call**: confirmation gate được gọi hai lần — dù hiện tại vẫn đúng hành vi nhờ compat alias, nhưng dễ gây bug khi refactor.

#### GAP 8: Secret chưa được quản lý bằng Kubernetes Secret

`GROQ_API_KEY` và `COPILOT_CONFIRMATION_SECRET` hiện đọc từ env var / `.env` file. Trên EKS, cần tạo Kubernetes Secret và inject qua `envFrom`.

### 1.4 Tổng hợp mức độ ưu tiên các GAP

| # | GAP | Mức độ | Blocker deploy? |
|---|---|---|---|
| 2 | gRPC address hardcode `localhost` + port review sai | 🔴 Nghiêm trọng | **Có** |
| 5 | Chưa có Dockerfile + Helm entry | 🔴 Nghiêm trọng | **Có** |
| 8 | Secret chưa quản lý bằng K8s Secret | 🔴 Nghiêm trọng | **Có** |
| 1 | `get_cart_tool` chưa implement (Core Intent 3b) | 🟡 Quan trọng | Không (thiếu feature) |
| 3 | OpenTelemetry chưa bật | 🟡 Quan trọng | Không (ảnh hưởng observability) |
| 4 | Session memory chưa persist | 🟡 Quan trọng | Không (ảnh hưởng UX) |
| 7 | Double confirmation gate trong cart_tool | 🟠 Cần sửa | Không (tiềm ẩn logic bug) |
| 6 | CORS wildcard | 🟠 Cần sửa | Không (security best practice) |

---

## Phần 2 — Integration Plan: Tích hợp vào hệ thống & đề xuất Infra

### 2.1 Kiến trúc tích hợp tổng quan

Shopping Copilot sẽ chạy như một **service độc lập trong namespace `techx-tf3`**, nhận request từ `frontend-proxy` (Envoy) theo path prefix `/api/copilot/`, giao tiếp nội bộ với các gRPC service qua Kubernetes Service DNS.

```
                    ┌──────────────────────────────────────────────────────┐
                    │            Kubernetes Namespace: techx-tf3           │
                    │                                                      │
User Browser ──────▶│  frontend-proxy (Envoy :8080)                       │
                    │    │                                                 │
                    │    ├──▶ /api/copilot/* ──▶ shopping-copilot:8001    │
                    │    │        │                                        │
                    │    │        ├──gRPC──▶ product-catalog:3550          │
                    │    │        ├──gRPC──▶ product-reviews:9090          │
                    │    │        ├──gRPC──▶ cart:7070                     │
                    │    │        ├──gRPC──▶ recommendation:8080           │
                    │    │        ├──gRPC──▶ currency:7001                 │
                    │    │        └──gRPC──▶ shipping:50051                │
                    │    │                                                 │
                    │    └──▶ (tất cả luồng hiện có giữ nguyên)           │
                    └──────────────────────────────────────────────────────┘
```

> **Nguyên tắc tích hợp:** Shopping Copilot **không thay thế** bất kỳ service nào đang chạy. Nó là service mới, chỉ **đọc** từ product-catalog, product-reviews, recommendation, currency, shipping. Duy nhất một thao tác ghi là `CartService.AddItem` — và luôn qua Confirmation Gate trước khi thực thi.

### 2.2 Các bước tích hợp chi tiết

#### Bước 1: Sửa gRPC address — đọc từ env var (team AI thực hiện)

Sửa tất cả tools để đọc địa chỉ gRPC từ environment variable thay vì hardcode:

**`tools/catalog_tool.py`:**
```python
import os
CATALOG_ADDR = os.getenv("CATALOG_ADDR", "product-catalog:3550")
```

**`tools/review_tool.py`** — sửa cả địa chỉ lẫn port sai:
```python
import os
# Sửa port từ 3551 → 9090 (đúng port của product-reviews theo ARCHITECTURE.md)
REVIEWS_ADDR = os.getenv("REVIEWS_ADDR", "product-reviews:9090")
```

**`tools/cart_tool.py`:**
```python
import os
CART_ADDR = os.getenv("CART_ADDR", "cart:7070")
```

#### Bước 2: Thêm `get_cart_tool` vào `cart_tool.py` (team AI thực hiện)

```python
@tool
def get_cart_tool(user_id: str) -> str:
    """
    Hữu ích khi người dùng muốn xem nội dung giỏ hàng hiện tại của mình.
    Chỉ cần user_id của người dùng.
    """
    channel = grpc.insecure_channel(CART_ADDR)
    stub = demo_pb2_grpc.CartServiceStub(channel)
    try:
        request = demo_pb2.GetCartRequest(user_id=user_id)
        response = stub.GetCart(request)
        if not response.items:
            return f"Giỏ hàng của {user_id} đang trống."
        lines = [f"- {item.product_id} | Số lượng: {item.quantity}" for item in response.items]
        return "Giỏ hàng hiện tại:\n" + "\n".join(lines)
    except grpc.RpcError as e:
        return f"Lỗi khi lấy giỏ hàng: {e.details()}"
    finally:
        channel.close()
```

Sau đó đăng ký trong `tools/__init__.py`:
```python
from tools.cart_tool import add_to_cart_tool, get_cart_tool

all_shopping_tools = [
    search_products_tool,
    get_product_reviews_tool,
    add_to_cart_tool,
    get_cart_tool,       # ← thêm mới
]
```

#### Bước 3: Tạo `Dockerfile` (team AI thực hiện)

Tạo file `shopping-copilot/Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')"

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
```

Đồng thời bỏ comment OTel packages trong `requirements.txt`:
```
opentelemetry-api>=1.20
opentelemetry-sdk>=1.20
opentelemetry-instrumentation-fastapi>=0.41b0
opentelemetry-exporter-otlp-proto-grpc>=1.20
```

#### Bước 4: Tạo Helm values file mới — `deploy/values-copilot.yaml` (team AI thực hiện)

Tạo file **mới tách biệt** — không sửa `values.yaml` gốc của chart để tránh conflict với baseline CDO đang quản lý:

```yaml
# deploy/values-copilot.yaml
# Shopping Copilot service — AIO02 TF3
# Ghép vào lệnh helm upgrade:
#   -f deploy/values-flagd-sync.yaml -f deploy/values-copilot.yaml
# KHÔNG dùng cùng values-observability.yaml + values-app-stamp.yaml

components:
  shopping-copilot:
    enabled: true
    useDefault:
      env: true                   # Kế thừa OTEL_SERVICE_NAME và OTel collector env mặc định
    image:
      tag: "1.0"
    service:
      port: 8001
    env:
      - name: PORT
        value: "8001"
      # gRPC addresses — trỏ tới service nội bộ (short DNS, cùng namespace)
      - name: CATALOG_ADDR
        value: "product-catalog:3550"
      - name: REVIEWS_ADDR
        value: "product-reviews:9090"
      - name: CART_ADDR
        value: "cart:7070"
      - name: RECO_ADDR
        value: "recommendation:8080"
      - name: CURRENCY_ADDR
        value: "currency:7001"
      - name: SHIPPING_ADDR
        value: "shipping:50051"
      # LLM config
      - name: GROQ_MODEL
        value: "llama-3.3-70b-versatile"
      # OTel — trỏ vào collector đã có trong cluster
      - name: OTEL_EXPORTER_OTLP_ENDPOINT
        value: "http://$(OTEL_COLLECTOR_NAME):4317"
    envOverrides:
      - name: GROQ_API_KEY
        valueFrom:
          secretKeyRef:
            name: shopping-copilot-secrets
            key: GROQ_API_KEY
      - name: COPILOT_CONFIRMATION_SECRET
        valueFrom:
          secretKeyRef:
            name: shopping-copilot-secrets
            key: COPILOT_CONFIRMATION_SECRET
    resources:
      requests:
        memory: "256Mi"
        cpu: "100m"
      limits:
        memory: "512Mi"
        cpu: "500m"
    livenessProbe:
      httpGet:
        path: /health
        port: 8001
      initialDelaySeconds: 15
      periodSeconds: 30
    readinessProbe:
      httpGet:
        path: /health
        port: 8001
      initialDelaySeconds: 10
      periodSeconds: 15
```

> **Lý do dùng short DNS:** Tất cả service chạy trong cùng namespace `techx-tf3`. Short DNS `product-catalog:3550` resolve đúng trong cùng namespace mà không cần FQDN.

#### Bước 5: Tạo Kubernetes Secret (CDO01 thực hiện — trước khi deploy)

```bash
# Tạo secret trước khi helm upgrade
# KHÔNG commit giá trị thật vào bất kỳ file tracked nào
kubectl -n techx-tf3 create secret generic shopping-copilot-secrets \
  --from-literal=GROQ_API_KEY=<REAL_GROQ_API_KEY> \
  --from-literal=COPILOT_CONFIRMATION_SECRET=<RANDOM_SECRET_32_CHARS>
```

> **Cảnh báo:** Gitleaks đang chạy trên pre-commit và GitHub Actions. Commit bất kỳ giá trị thật nào của secret vào file tracked sẽ bị chặn và ghi vào log vi phạm.

#### Bước 6: Cấu hình Envoy routing (CDO01 thực hiện)

Thêm route vào cấu hình Envoy của `frontend-proxy` để forward `/api/copilot/*` vào `shopping-copilot:8001`. Cách làm không phá cấu hình hiện có là patch qua ConfigMap hoặc Helm values.

**Route rule cần thêm** (vào virtual host listener `:8080`):
```yaml
- match:
    prefix: "/api/copilot/"
  route:
    prefix_rewrite: "/api/"    # strip /copilot → gọi /api/chat, /api/confirm
    cluster: shopping-copilot
    timeout: 60s               # LLM call có thể chậm hơn timeout mặc định
```

**Cluster definition:**
```yaml
- name: shopping-copilot
  connect_timeout: 5s
  type: STRICT_DNS
  lb_policy: ROUND_ROBIN
  load_assignment:
    cluster_name: shopping-copilot
    endpoints:
      - lb_endpoints:
          - endpoint:
              address:
                socket_address:
                  address: shopping-copilot
                  port_value: 8001
```

> **Bắt buộc:** Không được sửa filter `envoy.filters.http.fault` hay tham số `max_active_faults: 100` trong cấu hình Envoy hiện tại. Đây là cơ chế sự cố của BTC — gỡ hoặc thay đổi là vi phạm luật disqualify.

#### Bước 7: Build image và deploy (CDO01 thực hiện)

```bash
# 7.1 — Build image
cd Phase3-TF3-Infra-Sentinel/shopping-copilot
docker build -t shopping-copilot:1.0 .

# 7.2 — Tag và push lên ECR (thay <ACCOUNT> và <REGION>)
docker tag shopping-copilot:1.0 \
  <ACCOUNT>.dkr.ecr.<REGION>.amazonaws.com/techx-corp/shopping-copilot:1.0
docker push \
  <ACCOUNT>.dkr.ecr.<REGION>.amazonaws.com/techx-corp/shopping-copilot:1.0

# 7.3 — Deploy
NS=techx-tf3
REG=<ACCOUNT>.dkr.ecr.<REGION>.amazonaws.com/techx-corp

helm upgrade --install techx-corp ./techx-corp-chart -n $NS --create-namespace \
  --set default.image.repository=$REG \
  -f deploy/values-flagd-sync.yaml \
  -f deploy/values-copilot.yaml
```

> **Bắt buộc:** Luôn ghép `-f deploy/values-flagd-sync.yaml` trong mọi lần `helm upgrade`. Thiếu file này → flagd mất kết nối nguồn feature flag BTC → vi phạm luật chơi.

#### Bước 8: Migrate Session memory sang Valkey (sau khi service chạy ổn)

Thay thế in-memory `SessionStore` bằng Redis client kết nối vào Valkey đang có trong cluster:

```python
# memory/store.py — phiên bản production
import redis
import os

_redis = redis.Redis.from_url(
    os.getenv("VALKEY_ADDR", "redis://valkey-cart:6379"),
    db=1,          # DB 1 — tránh xung đột với cart service đang dùng DB 0
    decode_responses=True,
)
```

Thêm vào `values-copilot.yaml`:
```yaml
      - name: VALKEY_ADDR
        value: "redis://valkey-cart:6379"
```

> **Ràng buộc cứng:** Cart service (`valkey-cart`) đang dùng DB 0. Shopping Copilot **phải dùng DB 1 hoặc DB 2** — không được dùng DB 0 để tránh xung đột key.

### 2.3 Đề xuất Infra — không thêm tài nguyên mới (Budget-aware)

Với ngân sách $300/tuần/TF, **ưu tiên tái sử dụng** tài nguyên đã có:

| Tài nguyên | Cách tái sử dụng | Chi phí thêm |
|---|---|---|
| Envoy `frontend-proxy` | Thêm route `/api/copilot/` vào config hiện có | ~$0 |
| Valkey `valkey-cart` | Dùng DB index 1 (không deploy Valkey mới) | ~$0 |
| OTel collector → Jaeger/Prometheus/OpenSearch | Chỉ cần bật OTel SDK trong service | ~$0 |
| ECR repo `techx-corp` | Push thêm tag `shopping-copilot:1.0` | ~$0 (storage negligible) |
| Node EC2 hiện có | 1 pod mới, 256Mi–512Mi RAM, shared node | ~$5–10/tuần |

**Không cần thêm:**
- EKS node mới (pod nhỏ đủ fit vào node hiện có)
- Load balancer riêng (đã có Envoy)
- Database riêng (Valkey multi-DB)
- Dedicated Valkey (dùng chung instance, DB khác)

**Tùy chọn mở rộng khi cần** (chỉ khi traffic cao và có số liệu đo được):

```yaml
# HPA — chỉ thêm khi có bằng chứng cần scale, không bật mặc định
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: shopping-copilot-hpa
  namespace: techx-tf3
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: shopping-copilot
  minReplicas: 1
  maxReplicas: 3           # Tối đa 3 replica để kiểm soát chi phí
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

> **Lưu ý thiết kế:** HMAC token xác nhận trong Confirmation Gate là **stateless** — không phụ thuộc RAM server, nên hoạt động đúng ngay cả khi scale lên nhiều replica mà không cần session affinity.

### 2.4 Checklist trước khi bàn giao

**Team AI (AIO02) cần hoàn thành trước:**
```
[ ] Sửa port review_tool.py: 3551 → 9090
[ ] Sửa tất cả gRPC addr đọc từ env var (không hardcode localhost)
[ ] Tạo Dockerfile trong shopping-copilot/
[ ] Bật OTel packages trong requirements.txt
[ ] Thêm get_cart_tool vào cart_tool.py (Intent 3b — Core)
[ ] Đăng ký get_cart_tool vào tools/__init__.py
[ ] Fix double-call confirmation gate trong cart_tool.py
[ ] Tạo deploy/values-copilot.yaml
[ ] Restrict CORS về domain frontend thật (không để wildcard)
[ ] Verify unit tests pass: py -m pytest test_guardrails.py -v
```

**Team CDO01 (Platform/Infra) thực hiện:**
```
[ ] Tạo K8s Secret trước deploy:
    kubectl -n techx-tf3 create secret generic shopping-copilot-secrets ...
[ ] Build & push image lên ECR với tag shopping-copilot:1.0
[ ] Thêm route /api/copilot/ vào Envoy config (timeout 60s)
[ ] helm upgrade với -f values-flagd-sync.yaml -f values-copilot.yaml
[ ] Verify pod Running: kubectl -n techx-tf3 get pod -l app=shopping-copilot
[ ] Verify health: curl http://<host>:8080/api/copilot/health
```

**Joint verification (AI + CDO sau deploy):**
```
[ ] Test Intent 1: "Tìm tai nghe chống ồn dưới 50 đô" → ra sản phẩm đúng
[ ] Test Intent 2: hỏi review → câu trả lời có dẫn nguồn, không hallucinate
[ ] Test Intent 3: "Thêm 2 cái vào giỏ" → hiện nút Xác nhận → bấm → cập nhật giỏ
[ ] Test Intent 3b: "Giỏ hàng của tôi có gì?" → đọc đúng cart
[ ] Test guardrail Lớp 2: gửi "ignore previous instructions" → bị chặn 400
[ ] Test fallback: tắt product-catalog → trả friendly message, không crash
[ ] Kiểm tra trace trong Jaeger: tìm service "shopping-copilot"
[ ] Migrate SessionStore sang Valkey DB 1
[ ] Kiểm tra không có key conflict với cart service trên Valkey DB 0
```

### 2.5 Những gì KHÔNG được làm — ràng buộc cứng

| Quy tắc | Lý do |
|---|---|
| Không gỡ hoặc bypass `envoy.filters.http.fault` | Cơ chế sự cố của BTC — gỡ = disqualify |
| Không đổi token/URI trong `values-flagd-sync.yaml` | Mất kết nối nguồn feature flag BTC |
| Không commit `GROQ_API_KEY` hay `COPILOT_CONFIRMATION_SECRET` thật vào repo | Gitleaks chặn PR; vi phạm bảo mật |
| Không dùng Valkey DB 0 cho session/cache copilot | DB 0 đang dùng bởi cart service — xung đột key |
| Không dùng `values-observability.yaml` + `values-app-stamp.yaml` cùng lúc | Dùng chung = tắt hết pod (documented trong AGENTS.md) |
| Không để shopping-copilot tự gọi `PlaceOrder`, `EmptyCart`, `Charge` | DENIED trong Confirmation Gate — nếu bỏ guardrail = vi phạm thiết kế |

---

*Tài liệu này phản ánh trạng thái codebase tại `Phase3-TF3-Infra-Sentinel/shopping-copilot/` ngày 2026-07-09. Mọi thay đổi sau ngày này cần được cập nhật vào tài liệu bởi team thực hiện thay đổi.*
