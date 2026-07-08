from tools.catalog_tool import search_products_tool
from tools.cart_tool import add_to_cart_tool

print("--- TEST ĐỢT 1: THỬ NGHIỆM GỌI CATALOG TOOL ---")
# Test tìm kiếm sản phẩm (gọi gRPC SearchProducts lên EKS)
catalog_result = search_products_tool.invoke({"query": "Solar"})
print(catalog_result)

print("\n--- TEST ĐỢT 2: THỬ NGHIỆM GỌI CART TOOL ---")
# Test thêm vào giỏ (gọi gRPC AddItem lên EKS qua cổng bảo vệ)
cart_result = add_to_cart_tool.invoke({
    "user_id": "test_user_w1", 
    "product_id": "OLJCESPC7Z", 
    "quantity": 1
})
print(cart_result)