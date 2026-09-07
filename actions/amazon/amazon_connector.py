"""High-level Amazon.in connector for the desktop assistant.

Phase 1 exposes read-only order operations plus a manual login bootstrap.
Destructive actions remain disabled until their live workflows are separately
inspected and tested.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any
from urllib.parse import urljoin

from .amazon_browser import AmazonBrowser
from .schemas import AmazonActionResult, AmazonOrder


_ORDER_ID_RE = re.compile(r"\border\s*#?\s*([0-9][0-9-]{5,})\b", re.IGNORECASE)
_DELIVERY_RE = re.compile(
    r"\b(?:Delivered|Arriving|Arriving on|Delivery expected|Expected)\s+([0-9]{1,2}\s+[A-Za-z]{3,9}(?:\s+[0-9]{4})?)",
    re.IGNORECASE,
)
_PRICE_RE = re.compile(r"(?:₹|Rs\.?|INR\s*)\s*[0-9][0-9,]*(?:\.\d{1,2})?", re.IGNORECASE)
_TRACKING_RE = re.compile(r"\b(?:tracking(?:\s+(?:id|number))?|track(?:ing)?\s*(?:#|no\.?))\s*[:#-]?\s*([A-Z0-9][A-Z0-9-]{5,})\b", re.IGNORECASE)


class AmazonConnector:
    def __init__(
        self,
        profile_dir: str = "data/amazon/browser-profile",
        headless: bool = False,
    ) -> None:
        self.browser = AmazonBrowser(profile_dir=profile_dir, headless=headless)

    def close(self) -> None:
        self.browser.stop()

    def login(self) -> dict[str, Any]:
        page = self.browser.start()
        page.goto(AmazonBrowser.BASE_URL, wait_until="domcontentloaded", timeout=30_000)
        print("Sign in to Amazon.in manually in the opened browser.", file=sys.stderr)
        input("Press ENTER after login is complete... ")
        return {"success": True, "message": "Amazon browser session saved."}

    @staticmethod
    def _parse_order_text(
        text: str,
        *,
        title: str = "",
        price: str | None = None,
        order_url: str | None = None,
        tracking: str | None = None,
    ) -> AmazonOrder | None:
        """Parse fields from one live Amazon order-card's visible text."""
        order_match = _ORDER_ID_RE.search(text)
        if not order_match:
            return None

        status = None
        for candidate in ("Delivered", "Arriving", "Shipped", "Cancelled", "Canceled", "Refunded"):
            if re.search(rf"\b{re.escape(candidate)}\b", text, re.IGNORECASE):
                status = candidate
                break
        if re.search(r"\b(?:your delivery is still on the way|on the way)\b", text, re.IGNORECASE):
            status = "On the way"

        delivery_match = _DELIVERY_RE.search(text)
        tracking_match = _TRACKING_RE.search(text)
        price_match = _PRICE_RE.search(price or text)

        return AmazonOrder(
            order_id=order_match.group(1),
            title=title.strip(),
            price=price_match.group(0).strip() if price_match else None,
            status=status,
            delivery_date=delivery_match.group(1).strip() if delivery_match else None,
            tracking=(tracking or (tracking_match.group(1).strip() if tracking_match else None)),
            order_url=order_url,
        )

    @staticmethod
    def _first_text(locator) -> str:
        if locator.count() == 0:
            return ""
        return locator.first.inner_text(timeout=3_000).strip()

    @staticmethod
    def _first_href(locator, base_url: str) -> str | None:
        if locator.count() == 0:
            return None
        href = locator.first.get_attribute("href")
        if not href:
            return None
        return urljoin(base_url, href)

    @staticmethod
    def _product_title_and_url(card) -> tuple[str, str | None]:
        links = card.locator("a[href*='/dp/'], a[href*='/gp/product/']")
        for index in range(links.count()):
            link = links.nth(index)
            text = link.inner_text(timeout=3_000).strip()
            if text:
                return text, AmazonConnector._first_href(link, AmazonBrowser.BASE_URL)
        return "", None

    def list_orders(self, limit: int = 10) -> dict[str, Any]:
        self.browser.require_login()
        page = self.browser.open(AmazonBrowser.ORDERS_URL)
        cards = page.locator(
            "#ordersContainer > .js-order-card, "
            ".your-orders-content-container__content > .js-order-card, "
            ".your-orders-content-container__content > .order-card__list > .js-order-card"
        )

        card_count = cards.count()
        if card_count == 0:
            return {
                "success": False,
                "status": "selector_discovery_required",
                "message": "Amazon.in orders page opened, but no .js-order-card elements were found. The live orders DOM may have changed.",
                "url": page.url,
                "limit": limit,
            }

        orders: list[dict[str, Any]] = []
        for index in range(min(card_count, max(1, limit))):
            card = cards.nth(index)
            text = card.inner_text(timeout=5_000).strip()
            if not text:
                continue
            title, product_url = self._product_title_and_url(card)
            price = self._first_text(card.locator(".a-price, [class*='price'], span.a-color-price")) or None
            order_link = card.locator("a[href*='orderID='], a[href*='/gp/css/summary/']")
            order_url = self._first_href(order_link, AmazonBrowser.BASE_URL)
            parsed = self._parse_order_text(text, title=title, price=price, order_url=order_url or product_url)
            if parsed is not None:
                orders.append(parsed.to_dict())

        return {"success": True, "orders": orders, "count": len(orders), "url": page.url, "limit": limit}

    def find_order(self, query: str) -> dict[str, Any]:
        if not query.strip():
            return {"success": False, "message": "Order search query is empty."}
        result = self.list_orders(limit=20)
        if not result.get("success"):
            return result
        q = query.casefold()
        matches = [order for order in result["orders"] if q in order.get("title", "").casefold() or q in order.get("order_id", "").casefold()]
        return {"success": True, "orders": matches}

    def track_order(self, order_id: str) -> dict[str, Any]:
        if not order_id.strip():
            return {"success": False, "message": "Order ID is empty."}
        result = self.list_orders(limit=50)
        if not result.get("success"):
            return result
        matches = [o for o in result["orders"] if o.get("order_id") == order_id]
        if not matches:
            return {"success": False, "message": f"Order {order_id} was not found."}

        order = matches[0]
        order_url = order.get("order_url")
        if not order_url:
            return {"success": True, "order": order}

        page = self.browser.open(order_url)
        page.wait_for_timeout(1_000)
        body_text = page.locator("body").inner_text(timeout=10_000).strip()

        # Amazon's order-details page can expose the human-readable delivery
        # state and a Track package link rather than a conventional tracking ID.
        if re.search(r"\b(?:your delivery is still on the way|on the way)\b", body_text, re.IGNORECASE):
            order["status"] = "On the way"
        elif re.search(r"\bDelivered\b", body_text, re.IGNORECASE):
            order["status"] = "Delivered"

        delivery_match = _DELIVERY_RE.search(body_text)
        if delivery_match:
            order["delivery_date"] = delivery_match.group(1).strip()

        track_link = page.get_by_text("Track package", exact=True)
        if track_link.count():
            track_href = self._first_href(track_link, AmazonBrowser.BASE_URL)
            if track_href:
                order["tracking"] = track_href

                # Follow the real Amazon tracking page when available and
                # extract a conventional carrier/tracking number if Amazon
                # exposes one there. Keep the package URL when it does not.
                tracking_page = self.browser.open(track_href)
                tracking_page.wait_for_timeout(1_000)
                tracking_text = tracking_page.locator("body").inner_text(timeout=10_000).strip()
                tracking_match = _TRACKING_RE.search(tracking_text)
                if tracking_match:
                    order["tracking_number"] = tracking_match.group(1).strip()

        direct_tracking = _TRACKING_RE.search(body_text)
        if direct_tracking and not order.get("tracking_number"):
            order["tracking_number"] = direct_tracking.group(1).strip()

        return {"success": True, "order": order}

    def cancel_order(self, order_id: str, confirmed: bool = False) -> dict[str, Any]:
        if not confirmed:
            return AmazonActionResult(success=False, message="Cancellation requires explicit confirmation.").to_dict()
        return AmazonActionResult(success=False, message="Cancellation is deliberately disabled until the live Amazon.in workflow is tested.").to_dict()


def main() -> None:
    parser = argparse.ArgumentParser(description="Amazon.in connector bootstrap")
    parser.add_argument("--login", action="store_true")
    parser.add_argument("--list-orders", action="store_true")
    parser.add_argument("--find-order")
    parser.add_argument("--track")
    args = parser.parse_args()

    connector = AmazonConnector(headless=False)
    try:
        if args.login:
            result = connector.login()
        elif args.list_orders:
            result = connector.list_orders()
        elif args.find_order:
            result = connector.find_order(args.find_order)
        elif args.track:
            result = connector.track_order(args.track)
        else:
            result = {"success": False, "message": "No command specified."}
        print(json.dumps(result, indent=2, ensure_ascii=False))
    finally:
        connector.close()


if __name__ == "__main__":
    main()
