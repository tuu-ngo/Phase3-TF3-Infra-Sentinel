# Khai báo export tập trung các công cụ
# Chỉ đăng ký những tool đã được implement đầy đủ
from tools.catalog_tool import search_products_tool
from tools.cart_tool import add_to_cart_tool
from tools.review_tool import get_product_reviews_tool

# Danh sách toàn bộ công cụ cấp cho AI Agent — chỉ 3 tool đang có sẵn
# Khi đồng đội hoàn thiện thêm tool mới, import và thêm vào list này
all_shopping_tools = [
    search_products_tool,       # Tìm sản phẩm bằng ngôn ngữ tự nhiên (Read)
    get_product_reviews_tool,   # Hỏi-đáp grounded từ review thật (Read)
    add_to_cart_tool,           # Thêm vào giỏ hàng — CÓ Confirmation Gate (Write)
]