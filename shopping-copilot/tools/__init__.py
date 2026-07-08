# Khai báo export tập trung các công cụ
from tools.catalog_tool import search_products_tool
from tools.cart_tool import add_to_cart_tool

# Danh sách toàn bộ công cụ cấp cho AI Agent suy nghĩ
all_shopping_tools = [
    search_products_tool,
    add_to_cart_tool
]