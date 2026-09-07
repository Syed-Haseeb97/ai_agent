"""Safe unit tests for the Amazon connector scaffold."""
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
