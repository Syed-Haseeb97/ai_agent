"""Safe unit tests for the Amazon connector."""
from actions.amazon.amazon_connector import AmazonConnector


def test_cancel_requires_confirmation():
    connector = AmazonConnector()
    try:
        result = connector.cancel_order("408-test", confirmed=False)
        assert result["success"] is False
        assert "confirmation" in result["message"].lower()
    finally:
        connector.close()


def test_empty_find_order_is_rejected():
    connector = AmazonConnector()
    try:
        result = connector.find_order("   ")
        assert result["success"] is False
    finally:
        connector.close()


def test_parse_live_amazon_order_card_text():
    text = (
        "Delivered 18 June Package was delivered. "
        "ORDER # 404-1234567-7654321 "
        "You last purchased this item on 16 Jun 2026"
    )
    order = AmazonConnector._parse_order_text(
        text,
        title="Example Sports Product",
        price="₹1,299.00",
        order_url="https://www.amazon.in/gp/css/summary/detail.html?orderID=404-1234567-7654321",
    )

    assert order is not None
    assert order.order_id == "404-1234567-7654321"
    assert order.title == "Example Sports Product"
    assert order.price == "₹1,299.00"
    assert order.status == "Delivered"
    assert order.delivery_date == "18 June"
    assert order.order_url.endswith("orderID=404-1234567-7654321")


def test_parse_order_card_without_order_number_returns_none():
    assert AmazonConnector._parse_order_text("Delivered 18 June Package was delivered") is None
