"""Shared in-memory conversational sessions used by Ruby's chat surfaces."""
from __future__ import annotations

import threading
import uuid
from typing import Any, Dict, List


MAX_MESSAGE_CHARS = 8000
MAX_HISTORY_MESSAGES = 20
MAX_CONVERSATIONS = 100


class ChatService:
    """Own conversation history and call the same Gemini chat implementation for each UI.

    Histories are kept in memory only. Each conversation is isolated by its opaque ID and
    retains at most ten user/assistant turns. Provider errors are raised to the HTTP/UI layer;
    error strings are never stored as if they were assistant answers.
    """

    def __init__(self, client):
        self.client = client
        self._lock = threading.RLock()
        self._conversations: Dict[str, List[Dict[str, str]]] = {}

    def send(self, conversation_id: Any, message: Any) -> Dict[str, str]:
        if not isinstance(message, str) or not message.strip():
            raise ValueError("Message must not be empty.")
        message = message.strip()
        if len(message) > MAX_MESSAGE_CHARS:
            raise ValueError(f"Message must be at most {MAX_MESSAGE_CHARS} characters.")
        if conversation_id is None or conversation_id == "":
            conversation_id = uuid.uuid4().hex
        if not isinstance(conversation_id, str) or not (1 <= len(conversation_id) <= 128):
            raise ValueError("Invalid conversation ID.")

        # Serialize a turn so concurrent submissions cannot reorder one conversation.
        with self._lock:
            history = list(self._conversations.get(conversation_id, []))
            messages = [*history, {"role": "user", "content": message}]
            answer = self.client.chat(messages, max_output_tokens=4096, timeout_seconds=60)
            if not isinstance(answer, str) or not answer.strip():
                raise RuntimeError("Ruby returned an empty chat response.")
            updated = [*messages, {"role": "assistant", "content": answer.strip()}]
            self._conversations[conversation_id] = updated[-MAX_HISTORY_MESSAGES:]
            if len(self._conversations) > MAX_CONVERSATIONS:
                oldest = next(iter(self._conversations))
                if oldest != conversation_id:
                    self._conversations.pop(oldest, None)
            return {"conversationId": conversation_id, "response": answer.strip()}

    def clear(self, conversation_id: Any) -> None:
        if isinstance(conversation_id, str):
            with self._lock:
                self._conversations.pop(conversation_id, None)
