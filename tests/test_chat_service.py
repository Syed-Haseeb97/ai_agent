from __future__ import annotations

import unittest

from ai.chat_service import ChatService


class FakeClient:
    def __init__(self):
        self.calls = []
        self.answer = "first answer"

    def chat(self, messages, **kwargs):
        self.calls.append((list(messages), kwargs))
        return self.answer


class ChatServiceTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient()
        self.service = ChatService(self.client)

    def test_follow_up_receives_prior_user_and_assistant_turns(self):
        first = self.service.send("conversation-a", "Explain recursion.")
        self.client.answer = "It is when a function calls itself."
        second = self.service.send("conversation-a", "Give me a simple example.")

        self.assertEqual(first["response"], "first answer")
        self.assertEqual(second["conversationId"], "conversation-a")
        history = self.client.calls[1][0]
        self.assertEqual([item["role"] for item in history], ["user", "assistant", "user"])
        self.assertEqual(history[-1]["content"], "Give me a simple example.")
        self.assertEqual(self.client.calls[1][1]["max_output_tokens"], 4096)

    def test_conversations_are_isolated(self):
        self.service.send("conversation-a", "A private first topic")
        self.service.send("conversation-b", "A different topic")
        self.assertEqual(self.client.calls[1][0], [
            {"role": "user", "content": "A different topic"},
        ])

    def test_failed_turn_is_not_saved_as_assistant_context(self):
        class FailingClient(FakeClient):
            def chat(self, messages, **kwargs):
                self.calls.append((list(messages), kwargs))
                if len(self.calls) == 1:
                    raise RuntimeError("provider unavailable")
                return "recovered"

        client = FailingClient()
        service = ChatService(client)
        with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
            service.send("conversation-a", "This should not be committed")
        service.send("conversation-a", "Retry with a new message")
        self.assertEqual(client.calls[1][0], [
            {"role": "user", "content": "Retry with a new message"},
        ])

    def test_rejects_empty_and_oversized_messages(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            self.service.send("conversation-a", "  ")
        with self.assertRaisesRegex(ValueError, "8000"):
            self.service.send("conversation-a", "x" * 8001)


if __name__ == "__main__":
    unittest.main()
