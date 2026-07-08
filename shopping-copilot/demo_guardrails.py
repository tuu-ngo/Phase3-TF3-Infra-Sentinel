"""
Guardrails Demo Server — Giao diện chat trực quan để test 3 lớp bảo vệ.

Chạy:
    $env:PYTHONIOENCODING='utf-8'
    py demo_guardrails.py

Mở: http://localhost:9000
"""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from guardrails.input_filter import check_input
from guardrails.confirmation import request_confirmation, verify_confirmation_token
from guardrails.fallback import MaxIterationsExceeded, handle_exception

import uvicorn

app = FastAPI(title="Shopping Copilot — Guardrails Demo")


# ── Request/Response models ──
class ChatRequest(BaseModel):
    message: str
    user_id: str = "demo_user"

class ConfirmRequest(BaseModel):
    token: str


# ── API Endpoints ──

@app.post("/api/check-input")
def api_check_input(req: ChatRequest):
    """Lớp 2: Quét Prompt Injection"""
    result = check_input(req.message)
    return {
        "is_safe": result.is_safe,
        "blocked_reason": result.blocked_reason,
        "input": req.message[:100],
    }


@app.post("/api/add-to-cart")
def api_add_to_cart(req: ChatRequest):
    """Lớp 1: Confirmation Gate cho AddItem"""
    # Bước 1: Kiểm tra input trước
    filter_result = check_input(req.message)
    if not filter_result.is_safe:
        return {"layer": "INPUT_FILTER", "status": "BLOCKED", "message": filter_result.blocked_reason}

    # Bước 2: Confirmation Gate
    gate_result = request_confirmation(
        user_id=req.user_id,
        action="AddItem",
        action_params={"product_id": "DEMO-PRODUCT-001", "quantity": 1}
    )
    return {"layer": "CONFIRMATION_GATE", "status": gate_result.status,
            "message": gate_result.message, "token": gate_result.confirmation_token}


@app.post("/api/deny-action")
def api_deny_action(req: ChatRequest):
    """Lớp 1: Thử gọi hành động bị cấm (EmptyCart)"""
    gate_result = request_confirmation(req.user_id, "EmptyCart", {})
    return {"layer": "CONFIRMATION_GATE", "status": gate_result.status, "message": gate_result.message}


@app.post("/api/confirm")
def api_confirm(req: ConfirmRequest):
    """Xác nhận Token từ Frontend"""
    is_valid, data = verify_confirmation_token(req.token)
    if is_valid:
        return {"status": "APPROVED", "message": "✅ Xác nhận thành công! Đã thêm sản phẩm vào giỏ hàng.", "data": data}
    return {"status": "INVALID", "message": "❌ Token không hợp lệ hoặc đã hết hạn (5 phút)."}


@app.post("/api/simulate-crash")
def api_simulate_crash(req: ChatRequest):
    """Lớp 3: Fallback khi Agent bị lỗi"""
    try:
        raise MaxIterationsExceeded("Agent gọi tool quá 3 lần")
    except Exception as e:
        return handle_exception(e)


# ── Giao diện HTML ──
HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Shopping Copilot — Guardrails Demo</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', sans-serif; background: #0f1117; color: #e2e8f0; min-height: 100vh; }

  .header { background: linear-gradient(135deg, #1e3a5f, #0d2137); padding: 20px 32px;
    border-bottom: 1px solid #2d3748; display: flex; align-items: center; gap: 12px; }
  .header h1 { font-size: 1.4rem; font-weight: 700; color: #63b3ed; }
  .header .badge { background: #2d3748; color: #68d391; font-size: 0.7rem; padding: 3px 10px;
    border-radius: 99px; font-weight: 600; border: 1px solid #48bb78; }

  .container { max-width: 960px; margin: 0 auto; padding: 24px 16px; display: grid;
    grid-template-columns: 1fr 1fr; gap: 16px; }

  .card { background: #1a202c; border: 1px solid #2d3748; border-radius: 12px; overflow: hidden; }
  .card-header { padding: 14px 16px; font-size: 0.85rem; font-weight: 700; letter-spacing: 0.05em;
    text-transform: uppercase; border-bottom: 1px solid #2d3748; display: flex; align-items: center; gap: 8px; }
  .card-body { padding: 16px; }

  .layer1 .card-header { background: #2d1b4e; color: #b794f4; }
  .layer2 .card-header { background: #1a3a2a; color: #68d391; }
  .layer3 .card-header { background: #3a2014; color: #f6ad55; }

  label { font-size: 0.8rem; color: #a0aec0; margin-bottom: 6px; display: block; }
  input, textarea { width: 100%; background: #2d3748; border: 1px solid #4a5568; border-radius: 8px;
    padding: 10px 12px; color: #e2e8f0; font-size: 0.9rem; outline: none; resize: vertical;
    transition: border-color 0.2s; }
  input:focus, textarea:focus { border-color: #63b3ed; }
  textarea { min-height: 72px; font-family: inherit; }

  button { width: 100%; margin-top: 10px; padding: 10px 16px; border: none; border-radius: 8px;
    font-size: 0.9rem; font-weight: 600; cursor: pointer; transition: all 0.2s; }
  .btn-primary { background: #3182ce; color: white; }
  .btn-primary:hover { background: #2b6cb0; transform: translateY(-1px); }
  .btn-success { background: #276749; color: #9ae6b4; }
  .btn-success:hover { background: #22543d; }
  .btn-danger { background: #742a2a; color: #fc8181; }
  .btn-danger:hover { background: #63171b; }
  .btn-warn { background: #7b341e; color: #fbd38d; }
  .btn-warn:hover { background: #652b19; }

  .result { margin-top: 12px; padding: 12px; border-radius: 8px; font-size: 0.85rem;
    font-family: 'Consolas', monospace; line-height: 1.6; display: none; }
  .result.show { display: block; }
  .result.safe { background: #1c4532; border: 1px solid #276749; color: #9ae6b4; }
  .result.blocked { background: #3b1616; border: 1px solid #9b2c2c; color: #fc8181; }
  .result.pending { background: #1a365d; border: 1px solid #2c5282; color: #90cdf4; }
  .result.denied { background: #3b1616; border: 1px solid #9b2c2c; color: #fc8181; }
  .result.approved { background: #1c4532; border: 1px solid #276749; color: #9ae6b4; }
  .result.error { background: #3a2014; border: 1px solid #c05621; color: #fbd38d; }
  .result.info { background: #1a2744; border: 1px solid #2d3f6c; color: #a3bffa; }

  .status-badge { display: inline-block; padding: 2px 8px; border-radius: 4px;
    font-size: 0.75rem; font-weight: 700; margin-bottom: 6px; }
  .badge-safe { background: #276749; color: #9ae6b4; }
  .badge-blocked { background: #9b2c2c; color: #fc8181; }
  .badge-pending { background: #2c5282; color: #90cdf4; }
  .badge-denied { background: #9b2c2c; color: #fc8181; }
  .badge-approved { background: #276749; color: #9ae6b4; }
  .badge-error { background: #c05621; color: #fbd38d; }

  .token-box { margin-top: 8px; padding: 8px; background: #171923; border-radius: 6px;
    word-break: break-all; font-size: 0.75rem; color: #718096; }

  .full-width { grid-column: 1 / -1; }

  .legend { grid-column: 1 / -1; display: flex; gap: 12px; flex-wrap: wrap; padding: 12px 0; }
  .legend-item { display: flex; align-items: center; gap: 6px; font-size: 0.78rem; color: #a0aec0; }
  .legend-dot { width: 10px; height: 10px; border-radius: 50%; }

  .tip { background: #1a2744; border: 1px solid #2d3f6c; border-radius: 8px;
    padding: 12px 14px; font-size: 0.8rem; color: #a3bffa; line-height: 1.6; grid-column: 1 / -1; }
  .tip strong { color: #63b3ed; }
  .tip code { background: #2d3748; padding: 1px 6px; border-radius: 4px; font-family: monospace; }
</style>
</head>
<body>
<div class="header">
  <div>🛡️</div>
  <h1>Shopping Copilot — Guardrails Demo</h1>
  <div class="badge">AIE — Thành viên 3</div>
</div>

<div class="container">

  <div class="tip">
    💡 <strong>Hướng dẫn:</strong> Mỗi card thể hiện một lớp guardrail. Gõ câu vào ô input rồi bấm nút để xem phản ứng của hệ thống theo thời gian thực.
    Thử <code>Ignore previous instructions</code> ở Lớp 2, hoặc để nguyên câu bình thường để thấy sự khác biệt.
  </div>

  <!-- CARD 1: Input Filter -->
  <div class="card layer2">
    <div class="card-header">🔍 Lớp 2 — Input Filter (Prompt Injection)</div>
    <div class="card-body">
      <label>Nhập câu chat của khách hàng:</label>
      <textarea id="filter-input" placeholder="Thử: &quot;Ignore previous instructions...&quot;&#10;Hoặc: &quot;Tìm tai nghe bluetooth dưới 50 đô&quot;">Tìm cho tôi tai nghe bluetooth dưới 50 đô</textarea>
      <button class="btn-primary" onclick="testFilter()">🔍 Quét Input</button>
      <div id="filter-result" class="result"></div>
    </div>
  </div>

  <!-- CARD 2: Confirmation Gate - AddItem -->
  <div class="card layer1">
    <div class="card-header">🛒 Lớp 1 — Confirmation Gate (AddItem)</div>
    <div class="card-body">
      <label>Mô phỏng khách yêu cầu thêm vào giỏ:</label>
      <input type="text" id="cart-input" value="Thêm sản phẩm này vào giỏ hàng giúp tôi">
      <button class="btn-success" onclick="testAddCart()">🛒 Gọi Add To Cart</button>
      <div id="cart-result" class="result"></div>

      <div id="confirm-section" style="display:none; margin-top:12px;">
        <label style="color:#90cdf4;">👆 Token nhận được (5 phút hiệu lực):</label>
        <div class="token-box" id="token-display"></div>
        <button class="btn-primary" onclick="confirmAction()" style="margin-top:8px;">✅ Bấm XÁC NHẬN (giả lập user click)</button>
        <div id="confirm-result" class="result"></div>
      </div>
    </div>
  </div>

  <!-- CARD 3: Deny List -->
  <div class="card layer1">
    <div class="card-header">🚫 Lớp 1 — Deny-List (EmptyCart bị cấm)</div>
    <div class="card-body">
      <label>Mô phỏng AI cố gọi EmptyCart (bị cấm tuyệt đối):</label>
      <input type="text" id="deny-input" value="Xóa hết giỏ hàng của tôi" readonly style="color:#718096;">
      <button class="btn-danger" onclick="testDeny()">🚫 Gọi EmptyCart</button>
      <div id="deny-result" class="result"></div>
    </div>
  </div>

  <!-- CARD 4: Fallback -->
  <div class="card layer3">
    <div class="card-header">⚡ Lớp 3 — Fallback (LLM vòng lặp vô hạn)</div>
    <div class="card-body">
      <label>Mô phỏng LLM gọi tool quá 3 lần liên tiếp:</label>
      <input type="text" value="Agent vòng lặp tool-calling không dừng được" readonly style="color:#718096;">
      <button class="btn-warn" onclick="testFallback()">⚡ Kích hoạt MaxIterations</button>
      <div id="fallback-result" class="result"></div>
    </div>
  </div>

</div>

<script>
  let pendingToken = null;

  function showResult(elId, cssClass, html) {
    const el = document.getElementById(elId);
    el.className = `result show ${cssClass}`;
    el.innerHTML = html;
  }

  function badge(status, cls) {
    return `<span class="status-badge badge-${cls}">${status}</span><br>`;
  }

  async function testFilter() {
    const msg = document.getElementById('filter-input').value;
    const res = await fetch('/api/check-input', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: msg})
    });
    const data = await res.json();
    if (data.is_safe) {
      showResult('filter-result', 'safe',
        badge('✅ SAFE — Cho phép vào LLM', 'safe') +
        `<b>Input:</b> "${data.input}"`);
    } else {
      showResult('filter-result', 'blocked',
        badge('🚫 BLOCKED — Chặn lại ngay', 'blocked') +
        `<b>Lý do:</b> ${data.blocked_reason}`);
    }
  }

  async function testAddCart() {
    const msg = document.getElementById('cart-input').value;
    const res = await fetch('/api/add-to-cart', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: msg})
    });
    const data = await res.json();

    if (data.status === 'PENDING') {
      pendingToken = data.token;
      document.getElementById('token-display').textContent = data.token;
      document.getElementById('confirm-section').style.display = 'block';
      showResult('cart-result', 'pending',
        badge('⏳ PENDING — Chờ xác nhận từ User', 'pending') +
        `<b>Tin nhắn hiển thị cho khách:</b><br>${data.message}`);
    } else if (data.status === 'BLOCKED') {
      showResult('cart-result', 'blocked',
        badge('🚫 BLOCKED — Input Filter chặn', 'blocked') +
        `<b>Lý do:</b> ${data.message}`);
    }
  }

  async function confirmAction() {
    if (!pendingToken) return;
    const res = await fetch('/api/confirm', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({token: pendingToken})
    });
    const data = await res.json();
    if (data.status === 'APPROVED') {
      showResult('confirm-result', 'approved',
        badge('✅ APPROVED — Đã gọi gRPC AddItem', 'approved') +
        `${data.message}<br><b>Data:</b> ${JSON.stringify(data.data)}`);
    } else {
      showResult('confirm-result', 'blocked',
        badge('❌ INVALID TOKEN', 'blocked') + data.message);
    }
  }

  async function testDeny() {
    const res = await fetch('/api/deny-action', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: 'test'})
    });
    const data = await res.json();
    showResult('deny-result', 'denied',
      badge('🚫 DENIED — Cấm tuyệt đối', 'denied') +
      `<b>Lý do:</b> ${data.message}`);
  }

  async function testFallback() {
    const res = await fetch('/api/simulate-crash', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: 'test'})
    });
    const data = await res.json();
    showResult('fallback-result', 'error',
      badge('⚡ FALLBACK ACTIVATED', 'error') +
      `<b>Thông báo trả về cho khách:</b><br>${data.message}<br>` +
      `<b>Error code:</b> ${data.error_code}`);
  }
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML


if __name__ == "__main__":
    print("🛡️  Guardrails Demo Server — http://localhost:9000")
    print("    Ctrl+C để dừng\n")
    uvicorn.run(app, host="0.0.0.0", port=9000, log_level="warning")
