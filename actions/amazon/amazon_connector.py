"""High-level Amazon.in connector for the desktop assistant."""
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
_DELIVERY_RE = re.compile(r"\b(?:Delivered|Arriving|Arriving on|Delivery expected|Expected)\s+([0-9]{1,2}\s+[A-Za-z]{3,9}(?:\s+[0-9]{4})?)", re.IGNORECASE)
_PRICE_RE = re.compile(r"(?:₹|Rs\.?|INR\s*)\s*[0-9][0-9,]*(?:\.\d{1,2})?", re.IGNORECASE)
_TRACKING_RE = re.compile(r"\b(?:tracking(?:\s+(?:id|number))?|track(?:ing)?\s*(?:#|no\.?))\s*[:#-]?\s*([A-Z0-9][A-Z0-9-]{5,})\b", re.IGNORECASE)
_CANCEL_RE = re.compile(r"^(?:cancel(?:\s+items?(?:\s+in\s+this\s+order)?|\s+order)?|request\s+cancellation)$", re.IGNORECASE)
_RETURN_RE = re.compile(r"^(?:return(?:\s+items?)?|replace(?:\s+items?)?)$", re.IGNORECASE)
_RETURN_REASON_RE = re.compile(r"reason|why.*return|return.*reason", re.IGNORECASE)


class AmazonConnector:
    def __init__(self, profile_dir: str = "data/amazon/browser-profile", headless: bool = False) -> None:
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
    def _parse_order_text(text: str, *, title: str = "", price: str | None = None,
                          order_url: str | None = None, tracking: str | None = None) -> AmazonOrder | None:
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
            order_id=order_match.group(1), title=title.strip(),
            price=price_match.group(0).strip() if price_match else None,
            status=status,
            delivery_date=delivery_match.group(1).strip() if delivery_match else None,
            tracking=tracking or (tracking_match.group(1).strip() if tracking_match else None),
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
        return urljoin(base_url, href) if href else None

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
        cards = page.locator("#ordersContainer > .js-order-card, .your-orders-content-container__content > .js-order-card, .your-orders-content-container__content > .order-card__list > .js-order-card")
        if cards.count() == 0:
            return {"success": False, "status": "selector_discovery_required", "message": "Amazon.in orders page opened, but no .js-order-card elements were found. The live orders DOM may have changed.", "url": page.url, "limit": limit}
        orders: list[dict[str, Any]] = []
        for index in range(min(cards.count(), max(1, limit))):
            card = cards.nth(index)
            text = card.inner_text(timeout=5_000).strip()
            if not text:
                continue
            title, product_url = self._product_title_and_url(card)
            price = self._first_text(card.locator(".a-price, [class*='price'], span.a-color-price")) or None
            order_url = self._first_href(card.locator("a[href*='orderID='], a[href*='/gp/css/summary/']"), AmazonBrowser.BASE_URL)
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
        return {"success": True, "orders": [o for o in result["orders"] if q in o.get("title", "").casefold() or q in o.get("order_id", "").casefold()]}

    def _get_order(self, order_id: str) -> tuple[Any, dict[str, Any] | None]:
        result = self.list_orders(limit=50)
        if not result.get("success"):
            return None, None
        matches = [o for o in result["orders"] if o.get("order_id") == order_id]
        if not matches:
            return None, None
        order = matches[0]
        if not order.get("order_url"):
            return None, order
        page = self.browser.open(order["order_url"])
        page.wait_for_timeout(1_000)
        return page, order

    def track_order(self, order_id: str) -> dict[str, Any]:
        if not order_id.strip():
            return {"success": False, "message": "Order ID is empty."}
        page, order = self._get_order(order_id)
        if order is None:
            return {"success": False, "message": f"Order {order_id} was not found."}
        if page is None:
            return {"success": True, "order": order}
        body_text = page.locator("body").inner_text(timeout=10_000).strip()
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
                tracking_page = self.browser.open(track_href)
                tracking_page.wait_for_timeout(1_000)
                tracking_match = _TRACKING_RE.search(tracking_page.locator("body").inner_text(timeout=10_000).strip())
                if tracking_match:
                    order["tracking_number"] = tracking_match.group(1).strip()
        direct_tracking = _TRACKING_RE.search(body_text)
        if direct_tracking and not order.get("tracking_number"):
            order["tracking_number"] = direct_tracking.group(1).strip()
        return {"success": True, "order": order}

    @staticmethod
    def _cancel_controls(page) -> list[dict[str, str | None]]:
        controls = []
        for locator in (page.get_by_role("button"), page.get_by_role("link")):
            for index in range(locator.count()):
                element = locator.nth(index)
                try:
                    text = element.inner_text(timeout=1_000).strip()
                except Exception:
                    continue
                if _CANCEL_RE.search(text):
                    controls.append({"text": text, "href": element.get_attribute("href")})
        return controls

    @staticmethod
    def _return_controls(page) -> list[dict[str, str | None]]:
        controls = []
        for locator in (page.get_by_role("button"), page.get_by_role("link")):
            for index in range(locator.count()):
                element = locator.nth(index)
                try:
                    text = element.inner_text(timeout=1_000).strip()
                except Exception:
                    continue
                if _RETURN_RE.search(text):
                    controls.append({"text": text, "href": element.get_attribute("href")})
        return controls

    @staticmethod
    def _inspect_return_page(page) -> dict[str, Any]:
        """Read the return page without selecting a reason or submitting anything."""
        body = page.locator("body").inner_text(timeout=10_000).strip()
        headings: list[str] = []
        for index in range(page.locator("h1, h2, h3").count()):
            try:
                text = page.locator("h1, h2, h3").nth(index).inner_text(timeout=1_000).strip()
            except Exception:
                continue
            if text and text not in headings:
                headings.append(text)

        reasons: list[str] = []
        reason_controls = page.locator("input[type='radio'], input[type='checkbox']")
        for index in range(reason_controls.count()):
            control = reason_controls.nth(index)
            try:
                value = control.get_attribute("value")
                aria = control.get_attribute("aria-label")
                name = control.get_attribute("name")
                control_id = control.get_attribute("id")
                label = ""
                if control_id:
                    label_locator = page.locator(f"label[for='{control_id}']")
                    if label_locator.count():
                        label = label_locator.first.inner_text(timeout=1_000).strip()
                text = label or aria or value
                if text and (name or "reason" in text.casefold() or _RETURN_REASON_RE.search(text)) and text not in reasons:
                    reasons.append(text)
            except Exception:
                continue

        actions: list[dict[str, str | None]] = []
        for locator in (page.get_by_role("button"), page.get_by_role("link")):
            for index in range(locator.count()):
                element = locator.nth(index)
                try:
                    text = element.inner_text(timeout=1_000).strip()
                except Exception:
                    continue
                if text:
                    actions.append({"text": text, "href": element.get_attribute("href")})

        return {
            "url": page.url,
            "headings": headings,
            "body_preview": body[:4000],
            "reason_options": reasons,
            "actions": actions,
        }

    @staticmethod
    def _cancellation_unavailable_message(order: dict[str, Any]) -> str:
        status = str(order.get("status") or "").casefold()
        if status in {"on the way", "shipped", "delivered"}:
            return (
                "Amazon does not currently expose a Cancel or Request Cancellation control for this order. "
                "The order is already being processed/shipped, so no cancellation action is available from the live order page. "
                "If Amazon offers a return after delivery, use the return workflow instead."
            )
        return "Amazon does not currently expose a Cancel or Request Cancellation control for this order. No cancellation action is available from the live order page."

    def inspect_cancellation(self, order_id: str) -> dict[str, Any]:
        if not order_id.strip():
            return {"success": False, "message": "Order ID is empty."}
        page, order = self._get_order(order_id)
        if order is None:
            return {"success": False, "message": f"Order {order_id} was not found."}
        if page is None:
            return {"success": False, "message": "Order has no details URL."}
        controls = self._cancel_controls(page)
        return {
            "success": True,
            "order": order,
            "cancellation_available": bool(controls),
            "controls": controls,
            "message": "Cancellation control detected on the live Amazon page." if controls else self._cancellation_unavailable_message(order),
            "url": page.url,
        }

    def inspect_return(self, order_id: str) -> dict[str, Any]:
        """Open the live Return items workflow and inspect its next page without submitting."""
        if not order_id.strip():
            return {"success": False, "message": "Order ID is empty."}
        page, order = self._get_order(order_id)
        if order is None:
            return {"success": False, "message": f"Order {order_id} was not found."}
        if page is None:
            return {"success": False, "message": "Order has no details URL."}

        controls = self._return_controls(page)
        result: dict[str, Any] = {
            "success": True,
            "order": order,
            "return_available": bool(controls),
            "controls": controls,
            "url": page.url,
        }
        if not controls:
            result["message"] = "Amazon does not currently expose a Return or Replace control for this order."
            return result

        control = controls[0]
        return_url = control.get("href")
        if not return_url:
            result["message"] = "Amazon exposes Return items, but no navigable return URL was available."
            return result

        return_page = self.browser.open(urljoin(page.url, return_url))
        return_page.wait_for_timeout(1_500)
        workflow = self._inspect_return_page(return_page)
        result["return_url"] = return_page.url
        result["workflow"] = workflow
        result["message"] = "Live Return items workflow inspected. No return reason was selected and no return/refund request was submitted."
        return result

    def cancel_order(self, order_id: str, confirmed: bool = False) -> dict[str, Any]:
        if not confirmed:
            return AmazonActionResult(success=False, message="Cancellation requires explicit confirmation.").to_dict()
        page, order = self._get_order(order_id)
        if order is None:
            return AmazonActionResult(success=False, message=f"Order {order_id} was not found.").to_dict()
        if page is None:
            return AmazonActionResult(success=False, message="Order has no details URL.").to_dict()

        controls = self._cancel_controls(page)
        if not controls:
            return AmazonActionResult(success=False, message=self._cancellation_unavailable_message(order), order=order).to_dict()

        matching = None
        for text in ("Cancel items", "Cancel order", "Request cancellation", "Cancel"):
            for control in page.get_by_text(text, exact=True).all():
                matching = control
                break
            if matching is not None:
                break
        if matching is None:
            return AmazonActionResult(success=False, message="Cancellation control was detected but could not be safely targeted.", order=order).to_dict()

        matching.click()
        page.wait_for_timeout(1_000)

        final_names = ("Cancel selected items in this order", "Cancel selected items", "Request cancellation", "Confirm cancellation", "Cancel order")
        final_button = None
        for name in final_names:
            locator = page.get_by_role("button", name=name, exact=True)
            if locator.count():
                final_button = locator.first
                break
            locator = page.get_by_text(name, exact=True)
            if locator.count():
                final_button = locator.first
                break
        if final_button is not None:
            final_button.click()
            page.wait_for_timeout(1_500)

        body = page.locator("body").inner_text(timeout=10_000).strip()
        cancelled = bool(re.search(r"\b(?:cancellation requested|cancelled|canceled|order cancelled|order canceled)\b", body, re.IGNORECASE))
        if cancelled:
            return AmazonActionResult(success=True, message="Amazon cancellation workflow completed.", order=order).to_dict()
        return AmazonActionResult(success=False, message="Amazon cancellation control was activated, but the final cancellation state could not be verified. No further action was taken.", order=order).to_dict()


def main() -> None:
    parser = argparse.ArgumentParser(description="Amazon.in connector bootstrap")
    parser.add_argument("--login", action="store_true")
    parser.add_argument("--list-orders", action="store_true")
    parser.add_argument("--find-order")
    parser.add_argument("--track")
    parser.add_argument("--inspect-cancel")
    parser.add_argument("--inspect-return")
    parser.add_argument("--cancel")
    parser.add_argument("--confirmed", action="store_true", help="Explicitly confirm the destructive cancellation action")
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
        elif args.inspect_cancel:
            result = connector.inspect_cancellation(args.inspect_cancel)
        elif args.inspect_return:
            result = connector.inspect_return(args.inspect_return)
        elif args.cancel:
            result = connector.cancel_order(args.cancel, confirmed=args.confirmed)
        else:
            result = {"success": False, "message": "No command specified."}
        print(json.dumps(result, indent=2, ensure_ascii=False))
    finally:
        connector.close()


if __name__ == "__main__":
    main()
