import grpc
from langchain_core.tools import tool
import protos.demo_pb2 as demo_pb2
import protos.demo_pb2_grpc as demo_pb2_grpc
# Gọi hàm kiểm tra an toàn Excessive-Agency của Thành viên 3
from guardrails.confirmation import trigger_confirmation_gate

CART_ADDR = "localhost:7070"

@tool
def add_to_cart_tool(user_id: str, product_id: str, quantity: int) -> str:
    """
    Hữu ích khi người dùng yêu cầu thêm một hoặc nhiều sản phẩm cụ thể vào giỏ hàng của họ.
    Yêu cầu bắt buộc phải cung cấp đầy đủ thông tin: user_id, product_id, và số lượng (quantity).
    """
    # 🛡️ LỚP BẢO VỆ 1: Kích hoạt Cổng xác nhận (Confirmation Gate) chống AI tự ý hành động
    action_text = f"Thêm sản phẩm {product_id} (Số lượng: {quantity}) vào giỏ hàng."
    is_confirmed = trigger_confirmation_gate(user_id, action_text)
    
    if not is_confirmed:
        return "Hành động ghi giỏ hàng đã bị tạm dừng để chờ người dùng click nút 'Xác nhận' trên giao diện."

    # 🛡️ LỚP BẢO VỆ 2: Validate dữ liệu đầu vào cơ bản chống phá hoại
    if int(quantity) <= 0:
        return "Lỗi: Số lượng sản phẩm thêm vào giỏ phải lớn hơn 0."

    # Tiến hành gọi gRPC thật lên hệ thống của CDO sau khi qua các lớp bảo vệ
    channel = grpc.insecure_channel(CART_ADDR)
    stub = demo_pb2_grpc.CartServiceStub(channel)
    
    try:
        # Cấu trúc Object con lồng bên trong theo chuẩn Protobuf (CartItem)
        cart_item = demo_pb2.CartItem(product_id=product_id, quantity=int(quantity))
        
        # Đóng gói request tổng (AddItemRequest)
        request = demo_pb2.AddItemRequest(user_id=user_id, item=cart_item)
        
        # Thực thi gọi API
        stub.AddItem(request)
        return f"Thành công: Đã thêm {quantity} sản phẩm '{product_id}' vào giỏ hàng của tài khoản '{user_id}'."
        
    except grpc.RpcError as e:
        return f"Lỗi hệ thống khi tương tác với dịch vụ Giỏ hàng: {e.details()}"
    finally:
        channel.close()