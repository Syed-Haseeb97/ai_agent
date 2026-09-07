"""Local HTTP bridge between Ruby and the Amazon connector."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from actions.amazon.amazon_connector import AmazonConnector

app = FastAPI(title="Ruby Amazon Connector", version="0.1.0")
amazon = AmazonConnector(profile_dir="data/amazon/browser-profile", headless=False)


class FindOrderRequest(BaseModel):
    query: str


class TrackRequest(BaseModel):
    order_id: str


class CancelRequest(BaseModel):
    order_id: str
    confirmed: bool = False


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "amazon"}


@app.get("/amazon/status")
def status() -> dict:
    try:
        return {"success": True, "logged_in": amazon.browser.is_logged_in()}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@app.get("/amazon/orders")
def orders() -> dict:
    try:
        return amazon.list_orders()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/amazon/find-order")
def find_order(request: FindOrderRequest) -> dict:
    try:
        return amazon.find_order(request.query)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/amazon/track")
def track(request: TrackRequest) -> dict:
    try:
        return amazon.track_order(request.order_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/amazon/cancel")
def cancel(request: CancelRequest) -> dict:
    try:
        return amazon.cancel_order(request.order_id, confirmed=request.confirmed)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
