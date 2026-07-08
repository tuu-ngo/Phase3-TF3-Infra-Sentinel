# tools/review_tool.py
import grpc
from langchain_core.tools import tool
import protos.demo_pb2 as demo_pb2
import protos.demo_pb2_grpc as demo_pb2_grpc

REVIEWS_ADDR = "localhost:3551"

@tool
def get_product_reviews_tool(product_id: str) -> str:
    """
    Get real customer reviews for a specific product to provide grounded answers.
    Required input: product_id.
    """
    channel = grpc.insecure_channel(REVIEWS_ADDR)
    stub = demo_pb2_grpc.ProductReviewServiceStub(channel)
    
    try:
        # Khởi tạo request đúng chuẩn proto
        request = demo_pb2.GetProductReviewsRequest(product_id=product_id)
        response = stub.GetProductReviews(request)
        
        # Đọc chính xác trường 'product_reviews' từ file proto mẫu của bạn
        if not response.product_reviews:
            return f"Hệ thống báo: Hiện tại sản phẩm '{product_id}' chưa có lượt đánh giá nào."
            
        formatted_reviews = []
        for rev in response.product_reviews:
            # Trích xuất chính xác các trường: username, score, description
            username = rev.username if rev.username else "Anonymous"
            score = rev.score if rev.score else "N/A"
            description = rev.description if rev.description else "(No comment)"
            
            formatted_reviews.append(
                f"-[Khách hàng {username}]: Điểm số {score} | Nhận xét: {description}"
            )
            
        return f"Các đánh giá thực tế của người dùng về sản phẩm {product_id}:\n" + "\n".join(formatted_reviews)
        
    except grpc.RpcError as e:
        return f"Không thể lấy thông tin đánh giá do lỗi gRPC: {e.details()}"
    finally:
        channel.close()