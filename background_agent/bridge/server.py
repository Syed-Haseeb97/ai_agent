"""Runs the FastAPI app with uvicorn on a background thread, loopback only."""
from __future__ import annotations

import threading
import time
from typing import Optional

from .security import ensure_loopback
from .service import BridgeService


class BridgeServer:
    def __init__(self, service: BridgeService, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.service = service
        self.host = ensure_loopback(host)
        self.port = port
        self._server = None
        self._thread: Optional[threading.Thread] = None

    @property
    def base_url(self) -> str:
        host = "[::1]" if self.host == "::1" else self.host
        return f"http://{host}:{self.port}"

    def start(self, timeout: float = 10.0) -> None:
        import uvicorn  # imported lazily so the core package never needs web dependencies
        from .app import create_app

        config = uvicorn.Config(create_app(self.service), host=self.host, port=self.port,
                                log_level="warning", ws_max_size=65536)
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, name="bridge-server", daemon=True)
        self._thread.start()
        end = time.monotonic() + timeout
        while not self._server.started:
            if not self._thread.is_alive() or time.monotonic() > end:
                raise RuntimeError("bridge server failed to start (is the port already in use?)")
            time.sleep(0.02)
        self.port = self._server.servers[0].sockets[0].getsockname()[1]

    def stop(self, timeout: float = 10.0) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout)
