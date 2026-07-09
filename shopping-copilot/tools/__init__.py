# tools/__init__.py

from tools.catalog_tool import search_products_tool
from tools.cart_tool import add_to_cart_tool, get_cart_tool
from tools.review_tool import get_product_reviews_tool
from tools.recommendation_tool import get_recommendations_tool  # Thêm mới
from tools.currency_tool import convert_currency_tool          # Thêm mới
from tools.shipping_tool import get_shipping_quote_tool        # Thêm mới

# Danh sách đầy đủ tất cả các công cụ bàn giao cho AI Agent
all_shopping_tools = [
    # Nhóm Core (Bắt buộc)
    search_products_tool,
    get_product_reviews_tool,
    add_to_cart_tool,
    get_cart_tool,
    
    # Nhóm Mở rộng (Đua top)
    get_recommendations_tool,
    convert_currency_tool,
    get_shipping_quote_tool
]