"""Python <-> React bridge for the background agent (PR C1).

Importing this package needs NO web dependencies. FastAPI/uvicorn are only imported by
`bridge.app` / `bridge.server` / `bridge.dev_server`.
"""
from .confirmations import ConfirmationBroker, ConfirmationOutcome
from .events import EventHub, Subscription
from .protocol import BridgeError, ErrorCode, PROTOCOL_VERSION
from .security import (BridgeAuth, ensure_loopback, generate_token, get_or_create_token,
                       read_token_file, write_bridge_env, write_dev_env, write_token_file)
from .service import BridgeService

__all__ = ["BridgeAuth", "BridgeError", "BridgeService", "ConfirmationBroker", "ConfirmationOutcome",
           "ErrorCode", "EventHub", "PROTOCOL_VERSION", "Subscription", "ensure_loopback",
           "generate_token", "get_or_create_token", "read_token_file", "write_bridge_env",
           "write_dev_env", "write_token_file"]
