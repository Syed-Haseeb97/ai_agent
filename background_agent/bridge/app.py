"""FastAPI adapter. Intentionally THIN: all logic lives in BridgeService/BridgeAuth.

Requires: pip install fastapi "uvicorn[standard]"   (see requirements-bridge.txt)

NOTE: this module was written without FastAPI available in the build environment and has
NOT been executed there. tests/background_agent/test_bg_bridge_http.py exercises it and
auto-skips when FastAPI is missing - run it on your machine before relying on this layer.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from .protocol import (BridgeError, ErrorCode, PROTOCOL_VERSION, WS_AUTH_TIMEOUT_SECONDS,
                       WS_CLOSE_BAD_FRAME, WS_CLOSE_OVERFLOW, WS_CLOSE_POLICY, WS_CLOSE_TRY_LATER,
                       WS_CLOSE_UNAUTHORIZED, WS_HEARTBEAT_SECONDS)
from .service import BridgeService


def create_app(service: BridgeService):
    from fastapi import Depends, FastAPI, Request, WebSocket
    from fastapi.exceptions import RequestValidationError
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel

    class SubmitBody(BaseModel):
        goal: str

    class ConfirmBody(BaseModel):
        approved: bool

    app = FastAPI(title="Ruby background bridge", version=str(PROTOCOL_VERSION),
                  docs_url=None, redoc_url=None, openapi_url="/v1/openapi.json")
    # Explicit origins only (never "*"): needed because the Vite dev server is a different origin.
    app.add_middleware(CORSMiddleware, allow_origins=sorted(service.auth.allowed_origins),
                       allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])

    @app.exception_handler(BridgeError)
    async def _bridge_error(request: Request, exc: BridgeError):
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        err = BridgeError(ErrorCode.BAD_REQUEST, "invalid request body")
        return JSONResponse(status_code=err.http_status, content=err.to_dict())

    def require_auth(request: Request) -> None:
        service.auth.check_http(host=request.headers.get("host"), origin=request.headers.get("origin"),
                                authorization=request.headers.get("authorization"))

    auth = [Depends(require_auth)]

    @app.get("/v1/health")
    def health(request: Request) -> Any:
        service.auth.check_host(request.headers.get("host"))
        return {"ok": True, "protocol": PROTOCOL_VERSION}

    @app.get("/v1/state", dependencies=auth)
    def state() -> Any:
        return service.state()

    @app.post("/v1/tasks", status_code=201, dependencies=auth)
    def submit(body: SubmitBody) -> Any:
        return service.submit_task(body.goal)

    @app.get("/v1/tasks", dependencies=auth)
    def list_tasks(status: Optional[str] = None, limit: int = 100) -> Any:
        return {"tasks": service.list_tasks(status, limit)}

    @app.get("/v1/tasks/{task_id}", dependencies=auth)
    def get_task(task_id: str) -> Any:
        return service.get_task(task_id)

    @app.post("/v1/tasks/{task_id}/cancel", dependencies=auth)
    def cancel(task_id: str) -> Any:
        return service.cancel_task(task_id)

    @app.get("/v1/confirmations", dependencies=auth)
    def confirmations() -> Any:
        return {"confirmations": service.pending_confirmations()}

    @app.post("/v1/confirmations/{confirmation_id}", dependencies=auth)
    def respond(confirmation_id: str, body: ConfirmBody) -> Any:
        return service.respond_confirmation(confirmation_id, body.approved)

    @app.post("/v1/backend/reset-quarantine", dependencies=auth)
    def reset_quarantine() -> Any:
        return service.reset_backend_quarantine()

    @app.websocket("/v1/events")
    async def events(ws: WebSocket) -> None:
        try:
            service.auth.check_ws_upgrade(host=ws.headers.get("host"), origin=ws.headers.get("origin"))
        except BridgeError:
            await ws.close(code=WS_CLOSE_POLICY)
            return
        if not service.try_acquire_connection():
            await ws.close(code=WS_CLOSE_TRY_LATER)
            return
        sub = None
        reader: Optional[asyncio.Task] = None
        try:
            await ws.accept()
            # First frame must authenticate: {"type":"auth","token":...,"epoch":?,"last_seq":?}
            try:
                msg = await asyncio.wait_for(ws.receive_json(), timeout=WS_AUTH_TIMEOUT_SECONDS)
                if not isinstance(msg, dict) or msg.get("type") != "auth":
                    raise BridgeError(ErrorCode.UNAUTHORIZED, "first frame must be auth")
                service.auth.check_token(msg.get("token"))
            except BridgeError:
                await ws.close(code=WS_CLOSE_UNAUTHORIZED)
                return
            except Exception:  # timeout, bad JSON, disconnect
                await ws.close(code=WS_CLOSE_BAD_FRAME)
                return

            loop = asyncio.get_running_loop()
            wake = asyncio.Event()
            sub, frames = service.open_event_stream(
                msg.get("epoch"), msg.get("last_seq"),
                on_ready=lambda: loop.call_soon_threadsafe(wake.set))
            for frame in frames:
                await ws.send_json(frame)

            async def read_client() -> None:
                # Only used to notice a disconnect. Clients send nothing after the auth frame, and
                # this task never writes, so there is exactly one writer on the socket.
                while True:
                    await ws.receive_text()

            reader = asyncio.create_task(read_client())
            reader.add_done_callback(lambda t: t.cancelled() or t.exception())  # mark exception retrieved

            while True:
                while True:
                    frame = sub.get_nowait()
                    if frame is None:
                        break
                    await ws.send_json(frame)
                if sub.overflowed:
                    await ws.send_json({"v": PROTOCOL_VERSION, "type": "resync_required"})
                    await ws.close(code=WS_CLOSE_OVERFLOW)
                    return
                if sub.closed and not sub.has_items:  # hub shut down
                    await ws.close()
                    return
                wake.clear()
                if sub.has_items:
                    continue
                waiter = asyncio.create_task(wake.wait())
                done, _ = await asyncio.wait({waiter, reader}, timeout=WS_HEARTBEAT_SECONDS,
                                             return_when=asyncio.FIRST_COMPLETED)
                if waiter not in done:
                    waiter.cancel()
                if reader in done:
                    return  # client went away
                if not done:
                    await ws.send_json({"v": PROTOCOL_VERSION, "type": "heartbeat"})
        except Exception:
            pass  # disconnects surface as exceptions on send/receive; cleanup below
        finally:
            if reader is not None:
                reader.cancel()
            if sub is not None:
                sub.close()
            service.release_connection()

    return app
