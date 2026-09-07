"""High-level Amazon.in connector for the desktop assistant.

Phase 1 intentionally exposes only read-only order operations plus a manual
login bootstrap. Destructive actions are not wired until the live Amazon.in
DOM is inspected and tested in a dedicated account session.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .amazon_browser import AmazonBrowser
from .schemas import AmazonActionResult, AmazonOrder


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

    def list_orders(self, limit: int = 10) -> dict[str, Any]:
        self.browser.require_login()
        page = self.browser.open(AmazonBrowser.ORDERS_URL)

        # Amazon's customer-order DOM changes over time. We intentionally do
        # not guess production selectors here. The first implementation task
        # after login is to inspect the live DOM with Playwright codegen and
        # replace this guard with tested, resilient locators.
        return {
            "success": False,
            "status": "selector_discovery_required",
            "message": (
                "Amazon.in orders page opened successfully, but order parsing "
                "is disabled until live selectors are inspected and tested."
            ),
            "url": page.url,
            "limit": limit,
        }

    def find_order(self, query: str) -> dict[str, Any]:
        if not query.strip():
            return {"success": False, "message": "Order search query is empty."}
        result = self.list_orders(limit=20)
        if not result.get("success"):
            return result
        q = query.casefold()
        matches = [
            order for order in result["orders"]
            if q in order.get("title", "").casefold()
            or q in order.get("order_id", "").casefold()
        ]
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
        return {"success": True, "order": matches[0]}

    def cancel_order(self, order_id: str, confirmed: bool = False) -> dict[str, Any]:
        if not confirmed:
            return AmazonActionResult(
                success=False,
                message="Cancellation requires explicit confirmation.",
            ).to_dict()
        return AmazonActionResult(
            success=False,
            message="Cancellation is deliberately disabled until the live Amazon.in workflow is tested.",
        ).to_dict()


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
