"""
Guardrails Module — Export tập trung tất cả lớp bảo vệ.

Thành viên 2 (Agent) chỉ cần import:
    from guardrails import check_input, request_confirmation, verify_confirmation_token, with_fallback
"""

# Lớp 2: Input Filter — chặn Prompt Injection
from guardrails.input_filter import check_input, InputFilterResult

# Lớp 1: Confirmation Gate — chặn Excessive-Agency
from guardrails.confirmation import (
    request_confirmation,
    verify_confirmation_token,
    generate_confirmation_token,
    ConfirmationResult,
    DENIED_ACTIONS,
    CONFIRM_REQUIRED_ACTIONS,
)

# Lớp 3: Fallback — bọc lỗi LLM/gRPC
from guardrails.fallback import (
    with_fallback,
    handle_exception,
    make_error_response,
    MaxIterationsExceeded,
    CopilotServiceError,
    MAX_TOOL_ITERATIONS,
)
