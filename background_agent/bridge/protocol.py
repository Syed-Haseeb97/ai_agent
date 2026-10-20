"""Wire protocol constants and error type for the bridge (v1)."""
from __future__ import annotations

import enum
from typing import Any, Dict

PROTOCOL_VERSION = 1
MAX_WS_CONNECTIONS = 8
WS_AUTH_TIMEOUT_SECONDS = 5.0
WS_CLOSE_POLICY = 1008
WS_CLOSE_TRY_LATER = 1013
WS_CLOSE_UNAUTHORIZED = 4401
WS_CLOSE_OVERFLOW = 4408
WS_CLOSE_BAD_FRAME = 4400
WS_HEARTBEAT_SECONDS = 20.0


class ErrorCode(str, enum.Enum):
    BAD_REQUEST = "BAD_REQUEST"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    INVALID_GOAL = "INVALID_GOAL"
    QUEUE_FULL = "QUEUE_FULL"
    SHUTTING_DOWN = "SHUTTING_DOWN"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


_HTTP_STATUS = {
    ErrorCode.BAD_REQUEST: 400, ErrorCode.UNAUTHORIZED: 401, ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404, ErrorCode.INVALID_GOAL: 422, ErrorCode.QUEUE_FULL: 429,
    ErrorCode.SHUTTING_DOWN: 503, ErrorCode.SERVICE_UNAVAILABLE: 503,
}


class BridgeError(Exception):
    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    @property
    def http_status(self) -> int:
        return _HTTP_STATUS[self.code]

    def to_dict(self) -> Dict[str, Any]:
        return {"error": {"code": self.code.value, "message": self.message}}
