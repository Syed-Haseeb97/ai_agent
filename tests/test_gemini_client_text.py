from __future__ import annotations

import unittest

from ai.gemini_client import GeminiClient


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeModel:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def generate_content(self, prompt, *, generation_config, request_options):
        self.calls.append((prompt, generation_config, request_options))
        if self.error:
            raise self.error
        return self.response


class GeminiClientTextTests(unittest.TestCase):
    @staticmethod
    def client(model):
        client = GeminiClient.__new__(GeminiClient)
        client.model = model
        return client

    def test_generate_text_uses_the_existing_configured_model(self):
        model = FakeModel(FakeResponse('{"type":"finish"}'))
        result = self.client(model).generate_text("prompt", max_output_tokens=123)
        self.assertEqual(result, '{"type":"finish"}')
        self.assertEqual(model.calls, [("prompt", {"temperature": 0.1, "max_output_tokens": 123},
                                        {"timeout": 45})])

    def test_generate_text_rejects_empty_response_and_propagates_provider_errors(self):
        with self.assertRaisesRegex(RuntimeError, "empty response"):
            self.client(FakeModel(FakeResponse("  "))).generate_text("prompt")
        with self.assertRaisesRegex(OSError, "offline"):
            self.client(FakeModel(error=OSError("offline"))).generate_text("prompt")

    def test_generate_text_falls_back_when_primary_model_fails(self):
        primary = FakeModel(error=OSError("rate limited"))
        fallback = FakeModel(FakeResponse("answer from fallback"))
        client = self.client(primary)
        client.models = [primary, fallback]
        self.assertEqual(client.generate_text("prompt"), "answer from fallback")
        self.assertEqual(len(primary.calls), 1)
        self.assertEqual(len(fallback.calls), 1)
        self.assertIs(client.model, fallback)

    def test_chat_passes_conversation_history_as_provider_roles(self):
        model = FakeModel(FakeResponse("The second one is option B."))
        client = self.client(model)
        client.chat([
            {"role": "user", "content": "Which options are listed?"},
            {"role": "assistant", "content": "Option A and option B."},
            {"role": "user", "content": "What about the second one?"},
        ])
        contents = model.calls[0][0]
        self.assertEqual([item["role"] for item in contents], ["user", "model", "user"])
        self.assertEqual(contents[-1]["parts"], ["What about the second one?"])
        self.assertEqual(model.calls[0][1]["max_output_tokens"], 4096)


if __name__ == "__main__":
    unittest.main()
