"""HTTP adapter smoke tests; requires the optional bridge dependencies."""
from __future__ import annotations

import time
import unittest

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover - optional bridge dependencies
    TestClient = None

from background_agent.backends.mock import MockBackend
from ai.chat_service import ChatService
from background_agent.bridge.app import create_app
from background_agent.bridge.service import BridgeService
from background_agent.models import TERMINAL_STATUSES, TaskStatus
from background_agent.planner import Finish, ScriptedPlanner


class FakeChatClient:
    def __init__(self):
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append(list(messages))
        if len(messages) > 1:
            return "I remember the earlier message."
        return "Hello from Ruby chat."


@unittest.skipIf(TestClient is None, "install requirements-bridge.txt to test HTTP adapter")
class BridgeHttpTests(unittest.TestCase):
    def setUp(self):
        self.token = "test-token-with-more-than-16-characters"
        self.chat_client = FakeChatClient()
        self.service = BridgeService.create(
            MockBackend(),
            lambda _task: ScriptedPlanner([Finish("done", no_artifacts_expected=True)]),
            token=self.token,
            chat_service=ChatService(self.chat_client),
        )
        self.service.start()
        self.client = TestClient(create_app(self.service), base_url="http://127.0.0.1")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def tearDown(self):
        self.client.close()
        self.service.shutdown()

    def test_health_route_accepts_loopback_request(self):
        response = self.client.get("/v1/health")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["ok"])

    def test_authenticated_task_submission_and_state(self):
        submitted = self.client.post("/v1/tasks", headers=self.headers, json={"goal": "finish"})

        self.assertEqual(submitted.status_code, 201, submitted.text)
        task_id = submitted.json()["id"]
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            task = self.client.get(f"/v1/tasks/{task_id}", headers=self.headers)
            self.assertEqual(task.status_code, 200, task.text)
            if TaskStatus(task.json()["status"]) in TERMINAL_STATUSES:
                break
            time.sleep(0.01)
        self.assertEqual(task.json()["status"], TaskStatus.COMPLETED.value)
        state = self.client.get("/v1/state", headers=self.headers)
        self.assertEqual(state.status_code, 200, state.text)
        self.assertIn(task_id, {item["id"] for item in state.json()["tasks"]})

    def test_chat_route_preserves_context_without_submitting_a_task(self):
        first = self.client.post("/v1/chat", headers=self.headers,
                                 json={"conversationId": "test-conversation", "message": "Remember this."})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["response"], "Hello from Ruby chat.")
        second = self.client.post("/v1/chat", headers=self.headers,
                                  json={"conversationId": "test-conversation", "message": "What did I say?"})
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["response"], "I remember the earlier message.")
        self.assertEqual(len(self.chat_client.calls[1]), 3)
        self.assertEqual(self.service.list_tasks(), [])

    def test_chat_route_rejects_missing_credentials(self):
        response = self.client.post("/v1/chat", json={"message": "Hello"})
        self.assertEqual(response.status_code, 401, response.text)

    def test_routes_reject_missing_credentials(self):
        response = self.client.get("/v1/state")

        self.assertEqual(response.status_code, 401, response.text)
        self.assertEqual(response.json()["error"]["code"], "UNAUTHORIZED")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
