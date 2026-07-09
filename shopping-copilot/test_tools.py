# test_tools.py
from tools.catalog_tool import search_products_tool
from tools.cart_tool import add_to_cart_tool, get_cart_tool
from tools.review_tool import get_product_reviews_tool
from tools.recommendation_tool import get_recommendations_tool
from tools.currency_tool import convert_currency_tool
from tools.shipping_tool import get_shipping_quote_tool

print("====================================================")
print("🚀 SHOPPING COPILOT - COMPREHENSIVE TOOLS INTEGRATION TEST (Bypass confirmation.py is empty)")
print("====================================================\n")

# Mẫu dữ liệu kiểm thử đồng bộ
MOCK_USER = "test_user_w1"
# Sử dụng mã ID sản phẩm có thật thường dùng trong Catalog để dễ kiểm tra chéo data
MOCK_PRODUCT = "OLJCESPC7Z" 

# --- I. CORE INTENTS (4 intents) ---

print("--- TEST ĐỢT 1: CATALOG TOOL (Intent: Tìm sản phẩm) ---")
# Test tìm kiếm sản phẩm năng lượng mặt trời (gọi gRPC SearchProducts lên EKS Cluster)
catalog_result = search_products_tool.invoke({"query": "Solar"})
print(catalog_result)
print("-" * 60)

print("\n--- TEST ĐỢT 2: REVIEW TOOL (Intent: RAG Context - Khớp file proto) ---")
# Test lấy dữ liệu review thật để đối chiếu, phục vụ trả lời grounded 0 hallucinate
review_result = get_product_reviews_tool.invoke({"product_id": MOCK_PRODUCT})
print(review_result)
print("-" * 60)

print("\n--- TEST ĐỢT 3: CART TOOL (Intent: Ghi giỏ hàng - TEST MODE: BYPASS CONFIRMATION) ---")
# Test ghi giỏ hàng thành công vào Valkey Database trên AWS
cart_add_result = add_to_cart_tool.invoke({
    "user_id": MOCK_USER, 
    "product_id": MOCK_PRODUCT, 
    "quantity": 2
})
print(cart_add_result)
print("-" * 60)

print("\n--- TEST ĐỢT 4: GET CART TOOL (Intent: Đọc giỏ hàng) ---")
# Test đọc lại dữ liệu giỏ hàng vừa thêm thành công ở đợt test trước
cart_get_result = get_cart_tool.invoke({"user_id": MOCK_USER})
print(cart_get_result)
print("-" * 60)


# --- II. EXTENDED INTENTS (3 intents - Đua top) ---

print("\n--- TEST ĐỢT 5: RECOMMENDATION TOOL (Intent: Gợi ý kèm/Cross-sell) ---")
# Test lấy danh sách sản phẩm mua kèm thường thấy trên cụm EKS
reco_result = get_recommendations_tool.invoke({
    "product_id": MOCK_PRODUCT,
    "user_id": MOCK_USER
})
print(reco_result)
print("-" * 60)

print("\n--- TEST ĐỢT 6: CURRENCY TOOL (Intent: Quy đổi tiền tệ) ---")
# Thử nghiệm quy đổi từ 45 USD sang VND
currency_result = convert_currency_tool.invoke({
    "from_currency": "USD",
    "to_currency": "VND",
    "amount_units": 45
})
print(currency_result)
print("-" * 60)

print("\n--- TEST ĐỢT 7: SHIPPING TOOL (Intent: Dự toán phí Ship) ---")
# Thử nghiệm tính toán dự toán với một địa chỉ mẫu
shipping_result = get_shipping_quote_tool.invoke({
    "product_id": MOCK_PRODUCT,
    "quantity": 2,
    "street": "123 Nguyen Luong Bang",
    "city": "Da Nang",
    "country": "Vietnam",
    "zip_code": "550000"
})
print(shipping_result)
print("====================================================")
print("✅ COMPREHENSIVE TOOLS INTEGRATION TEST FINISHED. Ready for Agent-level integration.")
print("====================================================")