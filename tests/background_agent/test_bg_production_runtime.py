from __future__ import annotations

import json
import os
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import helpers  # noqa: F401

try:
    from fastapi.testclient import TestClient
    import httpx
except ImportError:  # pragma: no cover
    TestClient = None
    httpx = None

from background_agent.actions import FS_KINDS
from background_agent.backends.local_tools import LocalToolBackend
from background_agent.bridge.app import create_app
from background_agent.bridge.production_server import (build_production_service,
                                                       default_workspace, main)
from background_agent.bridge.server import BridgeServer
from background_agent.gemini_planner import GeminiPlanner
from background_agent.models import BackgroundTask, TaskLimits, TaskStatus, TERMINAL_STATUSES


class FakeGeminiClient:
    def __init__(self, *, api_key):
        if api_key != "unit-test-key":
            raise ValueError("wrong test key")
        self.started = threading.Event()
        self.release = threading.Event()

    def generate_text(self, prompt, *, max_output_tokens=4096, timeout_seconds=45):
        data = json.loads(prompt.split("Available data (JSON):\n", 1)[1])
        goal = data["goal"].lower()
        history = data["history"]
        if goal == "hold":
            self.started.set()
            self.release.wait(5)
        if goal == "confirm" and not history:
            return json.dumps({"type": "action", "kind": "fs.write", "params": {
                "path": "report.txt", "content": "verified report", "overwrite": True,
            }})
        if goal == "deny" and not history:
            return json.dumps({"type": "action", "kind": "fs.delete", "params": {"path": "victim.txt"}})
        if goal == "confirm" and history:
            return json.dumps({"type": "finish", "summary": "Created report.txt.",
                               "claimed_outputs": ["report.txt"], "no_artifacts_expected": False})
        if goal == "deny" and history:
            return json.dumps({"type": "finish", "summary": "The deletion was denied; no file was removed.",
                               "claimed_outputs": [], "no_artifacts_expected": True})
        summary = "Hello! I'm Ruby." if goal == "hello ruby" else "Stopped safely."
        return json.dumps({"type": "finish", "summary": summary,
                           "claimed_outputs": [], "no_artifacts_expected": True})


class ProductionRuntimeTests(unittest.TestCase):
    def test_missing_gemini_configuration_fails_clearly(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            with self.assertRaisesRegex(ValueError, "GEMINI_API_KEY is required"):
                build_production_service(workspace=Path("unused"))

    def test_launcher_builds_gemini_planner_with_filesystem_only_backend(self):
        captured = {}
        class FactoryBackend:
            name = "factory-backend"
        def backend_factory(root, **kwargs):
            captured["root"] = root
            captured.update(kwargs)
            return FactoryBackend()
        service = build_production_service(
            api_key="unit-test-key", workspace=Path("workspace"), token="runtime-test-token",
            gemini_client_factory=FakeGeminiClient, backend_factory=backend_factory,
        )
        try:
            task = BackgroundTask("hello", TaskLimits())
            self.assertIsInstance(service.manager._planner_factory(task), GeminiPlanner)
            self.assertEqual(service.auth.token, "runtime-test-token")
            self.assertEqual(captured["allowed_kinds"], FS_KINDS)
            self.assertFalse(captured["enable_browser"])
            self.assertEqual(captured["root"].name, "workspace")
        finally:
            service.shutdown()

    def test_workspace_default_uses_local_app_data(self):
        self.assertEqual(default_workspace({"LOCALAPPDATA": "C:/Users/test/AppData/Local"}),
                         Path("C:/Users/test/AppData/Local/Ruby/BackgroundWorkspace"))

    def test_missing_key_cli_reports_error_without_starting_bridge(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            self.assertEqual(main(["--bridge-env-file", "unused.env"]), 2)


@unittest.skipIf(TestClient is None, "install requirements-bridge.txt to test HTTP adapter")
class ProductionBridgeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.client_model = FakeGeminiClient(api_key="unit-test-key")
        self.service = build_production_service(
            api_key="unit-test-key", workspace=Path(self.temp.name),
            token="production-bridge-test-token",
            gemini_client_factory=lambda **_kwargs: self.client_model,
            backend_factory=lambda root, **kwargs: LocalToolBackend(root, **kwargs),
        )
        self.service.start()
        self.http = TestClient(create_app(self.service), base_url="http://127.0.0.1")
        self.headers = {"Authorization": f"Bearer {self.service.auth.token}"}

    def tearDown(self):
        self.client_model.release.set()
        self.http.close()
        self.service.shutdown()
        self.temp.cleanup()

    def _submit(self, goal):
        response = self.http.post("/v1/tasks", headers=self.headers, json={"goal": goal})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    def _until(self, predicate, timeout=5):
        end = time.monotonic() + timeout
        value = None
        while time.monotonic() < end:
            value = predicate()
            if value:
                return value
            time.sleep(0.01)
        self.fail(f"condition not reached; last value={value!r}")

    def _task(self, task_id):
        response = self.http.get(f"/v1/tasks/{task_id}", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _terminal_task(self, task_id):
        task = self._task(task_id)
        return task if TaskStatus(task["status"]) in TERMINAL_STATUSES else None

    def _pending_confirmation(self, task_id):
        response = self.http.get("/v1/confirmations", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        return next((item for item in response.json()["confirmations"]
                     if item["task_id"] == task_id), None)

    def test_existing_routes_run_gemini_confirm_cancel_and_return_results(self):
        state = self.http.get("/v1/state", headers=self.headers)
        self.assertEqual(state.status_code, 200, state.text)
        self.assertEqual(state.json()["backend"]["name"], "local-tools")

        hello_id = self._submit("Hello Ruby")
        hello = self._until(lambda: self._terminal_task(hello_id))
        self.assertEqual(hello["status"], "completed")
        self.assertEqual(hello["result"]["summary"], "Hello! I'm Ruby.")

        confirm_id = self._submit("confirm")
        confirmation = self._until(lambda: self._pending_confirmation(confirm_id))
        self.assertEqual(confirmation["task_id"], confirm_id)
        approved = self.http.post(f"/v1/confirmations/{confirmation['id']}", headers=self.headers,
                                  json={"approved": True})
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["resolution"], "approved")
        result = self._until(lambda: self._terminal_task(confirm_id))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(Path(result["result"]["outputs"][0]["path"]).name, "report.txt")
        self.assertTrue(result["result"]["verified"])

        deny_id = self._submit("deny")
        denial = self._until(lambda: self._pending_confirmation(deny_id))
        self.assertEqual(denial["task_id"], deny_id)
        rejected = self.http.post(f"/v1/confirmations/{denial['id']}", headers=self.headers,
                                  json={"approved": False})
        self.assertEqual(rejected.status_code, 200, rejected.text)
        self.assertEqual(rejected.json()["resolution"], "denied")
        self._until(lambda: self._terminal_task(deny_id))

        cancel_id = self._submit("hold")
        self.assertTrue(self.client_model.started.wait(2), "Gemini task did not enter the mock in-flight request")
        cancelled = self.http.post(f"/v1/tasks/{cancel_id}/cancel", headers=self.headers)
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertTrue(cancelled.json()["accepted"])
        self.client_model.release.set()
        final = self._until(lambda: self._terminal_task(cancel_id))
        self.assertEqual(final["status"], "cancelled")

    def test_production_service_starts_on_real_loopback_http_server(self):
        self.client_model.release.set()
        self.http.close()
        self.service.shutdown()
        self.service = build_production_service(
            api_key="unit-test-key", workspace=Path(self.temp.name) / "server-smoke",
            token="production-network-test-token",
            gemini_client_factory=lambda **_kwargs: FakeGeminiClient(api_key="unit-test-key"),
            backend_factory=lambda root, **kwargs: LocalToolBackend(root, **kwargs),
        )
        self.service.start()
        server = BridgeServer(self.service, host="127.0.0.1", port=0)
        server.start()
        try:
            headers = {"Authorization": f"Bearer {self.service.auth.token}"}
            with httpx.Client(base_url=server.base_url, headers=headers, timeout=5) as client:
                state = client.get("/v1/state")
                self.assertEqual(state.status_code, 200, state.text)
                response = client.post("/v1/tasks", json={"goal": "Hello Ruby"})
                self.assertEqual(response.status_code, 201, response.text)
                task_id = response.json()["id"]
                end = time.monotonic() + 5
                task = None
                while time.monotonic() < end:
                    task = client.get(f"/v1/tasks/{task_id}").json()
                    if TaskStatus(task["status"]) in TERMINAL_STATUSES:
                        break
                    time.sleep(0.01)
                self.assertEqual(task["status"], "completed")
                self.assertEqual(task["result"]["summary"], "Hello! I'm Ruby.")
        finally:
            self.service.shutdown()
            server.stop()


if __name__ == "__main__":
    unittest.main()
