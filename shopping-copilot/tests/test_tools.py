"""
tests/test_tools.py — Unit tests cho tất cả 5 tool files.

Môi trường:
  - Mock gRPC + REST — không cần port-forward EKS
  - Có thể chạy độc lập không cần GROQ_API_KEY

Chạy:
    pytest tests/test_tools.py -v
    pytest tests/test_tools.py -v --cov=tools
"""

import json
import logging
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

logger = logging.getLogger("test_tools")

# ── Helpers ──

class MockProtoMessage:
    """Mock object thay thế protobuf message — cho phép set attribute bằng constructor."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def CopyFrom(self, other):
        for attr in dir(other):
            if not attr.startswith("_"):
                setattr(self, attr, getattr(other, attr))

    def __iter__(self):
        return iter([])


def make_mock_stub(method_responses: dict):
    """
    Tạo mock gRPC stub với các method trả về response tương ứng.

    Args:
        method_responses: { "MethodName": return_value }
    """
    stub = MagicMock()
    for method, return_value in method_responses.items():
        mock_method = MagicMock(return_value=return_value)
        getattr(stub, method).return_value = return_value
    return stub


# ── Cart Tool Tests ──

class TestCartTool:
    """Tests cho tools/cart_tool.py — add_to_cart_tool + get_cart_tool."""

    @patch("tools.cart_tool.HAS_CONFIRMATION_SYSTEM", False)
    @patch("tools.cart_tool.grpc.insecure_channel")
    def test_add_to_cart_success(self, mock_channel):
        logger.info("Cart [add] — success: user adds 2x OLJCESPC7Z to cart")
        from tools.cart_tool import add_to_cart_tool, CART_ADDR

        channel_instance = MagicMock()
        mock_channel.return_value = channel_instance
        channel_instance.close = MagicMock()

        with patch("protos.demo_pb2_grpc.CartServiceStub") as mock_stub_cls:
            result = add_to_cart_tool.invoke({
                "user_id": "user_001",
                "product_id": "OLJCESPC7Z",
                "quantity": 2,
            })

        assert "Thành công" in result
        assert "OLJCESPC7Z" in result
        assert "user_001" in result

    @patch("tools.cart_tool.HAS_CONFIRMATION_SYSTEM", False)
    @patch("tools.cart_tool.grpc.insecure_channel")
    def test_add_to_cart_negative_quantity(self, mock_channel):
        logger.info("Cart [add] — edge: negative quantity should be rejected")
        from tools.cart_tool import add_to_cart_tool

        result = add_to_cart_tool.invoke({
            "user_id": "user_001",
            "product_id": "OLJCESPC7Z",
            "quantity": -1,
        })
        assert "Lỗi" in result
        assert "lớn hơn 0" in result

    @patch("tools.cart_tool.grpc.insecure_channel")
    def test_get_cart_empty(self, mock_channel):
        logger.info("Cart [get] — empty cart returns 'trống' message")
        from tools.cart_tool import get_cart_tool

        stub = MagicMock()
        mock_channel.return_value = MagicMock()
        mock_channel.return_value.close = MagicMock()

        empty_cart = MockProtoMessage(user_id="user_001", items=[])
        stub.GetCart.return_value = empty_cart

        with patch("protos.demo_pb2_grpc.CartServiceStub", return_value=stub):
            result = get_cart_tool.invoke({"user_id": "user_001"})

        assert "trống" in result

    @patch("tools.cart_tool.grpc.insecure_channel")
    def test_get_cart_with_items(self, mock_channel):
        logger.info("Cart [get] — cart with 2 items returns formatted list")
        from tools.cart_tool import get_cart_tool

        stub = MagicMock()
        mock_channel.return_value = MagicMock()
        mock_channel.return_value.close = MagicMock()

        item1 = MockProtoMessage(product_id="OLJCESPC7Z", quantity=2)
        item2 = MockProtoMessage(product_id="66VCHSJNUP", quantity=1)
        cart = MockProtoMessage(user_id="user_001", items=[item1, item2])
        stub.GetCart.return_value = cart

        with patch("protos.demo_pb2_grpc.CartServiceStub", return_value=stub):
            result = get_cart_tool.invoke({"user_id": "user_001"})

        assert "OLJCESPC7Z" in result
        assert "66VCHSJNUP" in result
        assert "Chi tiết giỏ hàng" in result

    @patch("tools.cart_tool.HAS_CONFIRMATION_SYSTEM", False)
    @patch("tools.cart_tool.grpc.insecure_channel")
    def test_add_to_cart_grpc_error(self, mock_channel):
        logger.info("Cart [add] — error: gRPC unavailable returns error message")
        from tools.cart_tool import add_to_cart_tool
        import grpc

        stub = MagicMock()
        mock_channel.return_value = MagicMock()
        mock_channel.return_value.close = MagicMock()

        error = grpc.RpcError()
        error.details = MagicMock(return_value="service unavailable")
        stub.AddItem.side_effect = error

        with patch("protos.demo_pb2_grpc.CartServiceStub", return_value=stub):
            result = add_to_cart_tool.invoke({
                "user_id": "user_001",
                "product_id": "OLJCESPC7Z",
                "quantity": 2,
            })

        assert "Lỗi hệ thống" in result


# ── Review Tool Tests ──

class TestReviewTool:
    """Tests cho tools/review_tool.py — get_product_reviews_tool."""

    @patch("tools.review_tool.grpc.insecure_channel")
    def test_get_reviews_success(self, mock_channel):
        logger.info("Review [get] — success: returns formatted reviews for product")
        from tools.review_tool import get_product_reviews_tool

        stub = MagicMock()
        mock_channel.return_value = MagicMock()
        mock_channel.return_value.close = MagicMock()

        review1 = MockProtoMessage(username="Alice", score="5", description="Tuyệt vời")
        review2 = MockProtoMessage(username="Bob", score="4", description="Tốt")
        response = MockProtoMessage(product_reviews=[review1, review2])
        stub.GetProductReviews.return_value = response

        with patch("protos.demo_pb2_grpc.ProductReviewServiceStub", return_value=stub):
            result = get_product_reviews_tool.invoke({"product_id": "OLJCESPC7Z"})

        assert "Alice" in result
        assert "Bob" in result
        assert "5" in result or "4" in result

    @patch("tools.review_tool.grpc.insecure_channel")
    def test_get_reviews_empty(self, mock_channel):
        logger.info("Review [get] — empty: no reviews for product returns message")
        from tools.review_tool import get_product_reviews_tool

        stub = MagicMock()
        mock_channel.return_value = MagicMock()
        mock_channel.return_value.close = MagicMock()

        response = MockProtoMessage(product_reviews=[])
        stub.GetProductReviews.return_value = response

        with patch("protos.demo_pb2_grpc.ProductReviewServiceStub", return_value=stub):
            result = get_product_reviews_tool.invoke({"product_id": "OLJCESPC7Z"})

        assert "chưa có lượt đánh giá" in result

    @patch("tools.review_tool.grpc.insecure_channel")
    def test_get_reviews_anonymous(self, mock_channel):
        logger.info("Review [get] — edge: empty fields fall back to defaults")
        from tools.review_tool import get_product_reviews_tool

        stub = MagicMock()
        mock_channel.return_value = MagicMock()
        mock_channel.return_value.close = MagicMock()

        review = MockProtoMessage(username="", score="", description="")
        response = MockProtoMessage(product_reviews=[review])
        stub.GetProductReviews.return_value = response

        with patch("protos.demo_pb2_grpc.ProductReviewServiceStub", return_value=stub):
            result = get_product_reviews_tool.invoke({"product_id": "OLJCESPC7Z"})

        assert "Anonymous" in result

    @patch("tools.review_tool.grpc.insecure_channel")
    def test_get_reviews_grpc_error(self, mock_channel):
        logger.info("Review [get] — error: gRPC down returns error message")
        from tools.review_tool import get_product_reviews_tool
        import grpc

        stub = MagicMock()
        mock_channel.return_value = MagicMock()
        mock_channel.return_value.close = MagicMock()

        error = grpc.RpcError()
        error.details = MagicMock(return_value="service down")
        stub.GetProductReviews.side_effect = error

        with patch("protos.demo_pb2_grpc.ProductReviewServiceStub", return_value=stub):
            result = get_product_reviews_tool.invoke({"product_id": "OLJCESPC7Z"})

        assert "lỗi" in result.lower()


# ── Recommendation Tool Tests ──

class TestRecommendationTool:
    """Tests cho tools/recommendation_tool.py — get_recommendations_tool."""

    @patch("tools.recommendation_tool.grpc.insecure_channel")
    def test_get_recommendations_success(self, mock_channel):
        logger.info("Recommendation [get] — success: returns related product IDs")
        from tools.recommendation_tool import get_recommendations_tool

        stub = MagicMock()
        mock_channel.return_value = MagicMock()
        mock_channel.return_value.close = MagicMock()

        response = MockProtoMessage(product_ids=["66VCHSJNUP", "L9ECAV7KIM", "0PUK6V6EV0"])
        stub.ListRecommendations.return_value = response

        with patch("protos.demo_pb2_grpc.RecommendationServiceStub", return_value=stub):
            result = get_recommendations_tool.invoke({
                "product_id": "OLJCESPC7Z",
                "user_id": "user_001",
            })

        assert "66VCHSJNUP" in result
        assert "0PUK6V6EV0" in result

    @patch("tools.recommendation_tool.grpc.insecure_channel")
    def test_get_recommendations_empty(self, mock_channel):
        logger.info("Recommendation [get] — empty: no recommendations for unknown product")
        from tools.recommendation_tool import get_recommendations_tool

        stub = MagicMock()
        mock_channel.return_value = MagicMock()
        mock_channel.return_value.close = MagicMock()

        response = MockProtoMessage(product_ids=[])
        stub.ListRecommendations.return_value = response

        with patch("protos.demo_pb2_grpc.RecommendationServiceStub", return_value=stub):
            result = get_recommendations_tool.invoke({
                "product_id": "UNKNOWN123",
                "user_id": "user_001",
            })

        assert "không có gợi ý" in result

    @patch("tools.recommendation_tool.grpc.insecure_channel")
    def test_get_recommendations_grpc_error(self, mock_channel):
        logger.info("Recommendation [get] — error: gRPC timeout returns error message")
        from tools.recommendation_tool import get_recommendations_tool
        import grpc

        stub = MagicMock()
        mock_channel.return_value = MagicMock()
        mock_channel.return_value.close = MagicMock()

        error = grpc.RpcError()
        error.details = MagicMock(return_value="timeout")
        stub.ListRecommendations.side_effect = error

        with patch("protos.demo_pb2_grpc.RecommendationServiceStub", return_value=stub):
            result = get_recommendations_tool.invoke({
                "product_id": "OLJCESPC7Z",
                "user_id": "user_001",
            })

        assert "Lỗi" in result


# ── Currency Tool Tests ──

class TestCurrencyTool:
    """Tests cho tools/currency_tool.py — convert_currency_tool."""

    @patch("tools.currency_tool.grpc.insecure_channel")
    def test_convert_currency_success(self, mock_channel):
        logger.info("Currency [convert] — success: USD→VND returns converted amount")
        from tools.currency_tool import convert_currency_tool

        stub = MagicMock()
        mock_channel.return_value = MagicMock()
        mock_channel.return_value.close = MagicMock()

        response = MockProtoMessage(units=25000, nanos=0, currency_code="VND")
        stub.Convert.return_value = response

        with patch("protos.demo_pb2_grpc.CurrencyServiceStub", return_value=stub):
            result = convert_currency_tool.invoke({
                "from_currency": "USD",
                "to_currency": "VND",
                "amount_units": 1,
            })

        assert "25000" in result
        assert "VND" in result
        assert "USD" in result

    @patch("tools.currency_tool.grpc.insecure_channel")
    def test_convert_currency_grpc_error(self, mock_channel):
        logger.info("Currency [convert] — error: gRPC unavailable returns error message")
        from tools.currency_tool import convert_currency_tool
        import grpc

        stub = MagicMock()
        mock_channel.return_value = MagicMock()
        mock_channel.return_value.close = MagicMock()

        error = grpc.RpcError()
        error.details = MagicMock(return_value="currency service unavailable")
        stub.Convert.side_effect = error

        with patch("protos.demo_pb2_grpc.CurrencyServiceStub", return_value=stub):
            result = convert_currency_tool.invoke({
                "from_currency": "USD",
                "to_currency": "EUR",
                "amount_units": 100,
            })

        assert "Lỗi" in result


# ── Shipping Tool Tests ──

class TestShippingTool:
    """Tests cho tools/shipping_tool.py — get_shipping_quote_tool."""

    @patch("tools.shipping_tool.requests.get")
    def test_get_shipping_quote_vietnam(self, mock_get):
        logger.info("Shipping [quote] — success: Vietnam address returns cost quote")
        from tools.shipping_tool import get_shipping_quote_tool

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "cost_usd": {"units": "5", "currency_code": "USD"}
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = get_shipping_quote_tool.invoke({
            "street": "123 Le Loi",
            "city": "Ho Chi Minh",
            "country": "Vietnam",
            "zip_code": "70000",
        })

        assert "5" in result
        assert "USD" in result
        assert "Vietnam" in result or "vietnam" in result

    def test_get_shipping_quote_international(self):
        logger.info("Shipping [quote] — guardrail: non-Vietnam country is rejected")
        from tools.shipping_tool import get_shipping_quote_tool

        result = get_shipping_quote_tool.invoke({
            "street": "123 Main St",
            "city": "New York",
            "country": "USA",
            "zip_code": "10001",
        })

        assert "only authorized" in result or "domestic" in result

    @patch("tools.shipping_tool.requests.get")
    def test_get_shipping_quote_http_error(self, mock_get):
        logger.info("Shipping [quote] — error: HTTP connection refused returns error")
        from tools.shipping_tool import get_shipping_quote_tool
        import requests

        mock_get.side_effect = requests.exceptions.RequestException("Connection refused")

        result = get_shipping_quote_tool.invoke({
            "street": "1 Le Duan",
            "city": "Hanoi",
            "country": "Vietnam",
            "zip_code": "10000",
        })

        assert "Error" in result or "error" in result

    @patch("tools.shipping_tool.requests.get")
    def test_get_shipping_quote_invalid_json(self, mock_get):
        logger.info("Shipping [quote] — error: invalid JSON response returns error")
        from tools.shipping_tool import get_shipping_quote_tool

        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = get_shipping_quote_tool.invoke({
            "street": "1 Le Duan",
            "city": "Hanoi",
            "country": "Vietnam",
            "zip_code": "10000",
        })

        assert "Error" in result


# ── Tool Registration Tests ──

class TestToolRegistration:
    """Kiểm tra tools/__init__.py export đúng danh sách tools."""

    def test_all_shopping_tools_listed(self):
        logger.info("Registration — verify all 6 tools are exported from tools/__init__.py")
        from tools import all_shopping_tools

        tool_names = {t.name for t in all_shopping_tools}
        assert "add_to_cart_tool" in tool_names
        assert "get_cart_tool" in tool_names
        assert "get_product_reviews_tool" in tool_names
        assert "get_recommendations_tool" in tool_names
        assert "convert_currency_tool" in tool_names
        assert "get_shipping_quote_tool" in tool_names

    def test_each_tool_has_description(self):
        logger.info("Registration — verify every tool has a non-empty description")
        from tools import all_shopping_tools

        for t in all_shopping_tools:
            assert t.description, f"Tool '{t.name}' thiếu description"
