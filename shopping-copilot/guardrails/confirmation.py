def trigger_confirmation_gate(user_id: str, action_description: str) -> bool:
    """
    Hàm giả lập Cổng xác nhận (Confirmation Gate).
    Trong thực tế tuần 2, hàm này sẽ ném trạng thái PENDING về Frontend.
    Hiện tại chạy Local mặc định trả về True để test luồng gRPC Client.
    """
    print(f"\n🛡️  [GUARDRAIL SECURITY] Yêu cầu ghi từ User '{user_id}': {action_description}")
    return True