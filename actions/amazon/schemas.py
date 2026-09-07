"""Stable data structures returned by the Amazon connector."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class AmazonOrder:
    order_id: str
    title: str
    price: Optional[str] = None
    status: Optional[str] = None
    delivery_date: Optional[str] = None
    tracking: Optional[str] = None
    order_url: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AmazonActionResult:
    success: bool
    message: str
    order: Optional[dict] = None

    def to_dict(self) -> dict:
        return asdict(self)
