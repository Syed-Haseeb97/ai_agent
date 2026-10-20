"""Execution-mode routing: dispatcher unit tests and HTTP adapter coverage."""
from __future__ import annotations

import threading
import time
import unittest
from types import SimpleNamespace

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover - optional bridge dependencies
    TestClient = None

from background_agent.backends.mock import MockBackend
from background_agent.bridge.app import create_app
from background_agent.bridge.cursor_control import CursorControlTasks, action_target
from background_agent.bridge.execution import (ExecutionMode, TaskDispatcher,
                                                parse_execution_mode)
from background_agent.bridge.protocol import BridgeError, ErrorCode
from background_agent.bridge.service import BridgeService
from background_agent.models import TERMINAL_STATUSES, TaskStatus
from background_agent.planner import Finish, ScriptedPlanner

TERMINAL_VALUES = {status.value for status in TERMINAL_STATUSES}
TOKEN = "execution-routing-test-token"


class FakeAgent:
    def __init__(self, status: str = "completed", message: str = "Desktop task finished.") -> None:
        self.status = status
        self.message = message

    def run(self, goal: str):
        return SimpleNamespace(status=self.status, message=self.message, turns=1)

    def stop(self) -> None:
        pass


class DispatcherTests(unittest.TestCase):
    def test_missing_mode_defaults_to_task_doing(self):
        dispatcher = TaskDispatcher({mode: lambda goal: {"id": "x", "goal": goal}
                                     for mode in ExecutionMode})

        submission = dispatcher.dispatch("finish", None)

        self.assertEqual(submission.execution_mode, ExecutionMode.TASK_DOING)
        self.assertEqual(submission.http_status, 201)
        self.assertEqual(submission.execution_environment, "foreground")
        self.assertEqual(submission.task["execution_mode"], "task_doing")
        self.assertEqual(submission.task["execution_environment"], "foreground")

    def test_each_mode_delegates_to_its_own_handler_and_is_tagged(self):
        calls = []
        handlers = {}
        for mode in ExecutionMode:
            def handler(goal, mode=mode):
                calls.append((mode, goal))
                return {"id": mode.value, "goal": goal, "status": "queued"}

            handlers[mode] = handler
        dispatcher = TaskDispatcher(handlers)

        for mode in ExecutionMode:
            submission = dispatcher.dispatch("do it", mode.value)
            self.assertEqual(submission.execution_mode, mode)
            self.assertEqual(submission.task["execution_mode"], mode.value)

        self.assertEqual(calls, [(mode, "do it") for mode in ExecutionMode])
        self.assertEqual(dispatcher.dispatch("x", "background_task").http_status, 202)
        self.assertEqual(dispatcher.dispatch("x", "cursor_control").http_status, 202)
        self.assertEqual(dispatcher.dispatch("x", "cursor_control").execution_environment, "desktop")
        self.assertEqual(dispatcher.dispatch("x", "background_task").execution_environment, "background")

    def test_unknown_mode_is_rejected(self):
        dispatcher = TaskDispatcher({mode: lambda goal: {"id": "x"} for mode in ExecutionMode})

        with self.assertRaises(BridgeError) as ctx:
            dispatcher.dispatch("finish", "teleport")

        self.assertEqual(ctx.exception.code, ErrorCode.BAD_REQUEST)

    def test_goal_is_validated_before_dispatch(self):
        dispatcher = TaskDispatcher({mode: lambda goal: {"id": "x"} for mode in ExecutionMode})

        with self.assertRaises(BridgeError) as ctx:
            dispatcher.dispatch("   ", "task_doing")

        self.assertEqual(ctx.exception.code, ErrorCode.INVALID_GOAL)

    def test_incomplete_handler_table_fails_fast(self):
        with self.assertRaises(ValueError):
            TaskDispatcher({ExecutionMode.TASK_DOING: lambda goal: {}})

    def test_parse_mode_is_exact(self):
        self.assertEqual(parse_execution_mode("cursor_control"), ExecutionMode.CURSOR_CONTROL)
        with self.assertRaises(BridgeError):
            parse_execution_mode("CURSOR_CONTROL")

    def test_cursor_targets_are_extracted_for_the_orb(self):
        self.assertEqual(action_target(SimpleNamespace(arguments={"x": "400", "y": 900})),
                         {"x": 400, "y": 900})
        self.assertEqual(action_target(SimpleNamespace(arguments={"x": -20, "y": 1200})),
                         {"x": 0, "y": 999})
        self.assertIsNone(action_target(SimpleNamespace(arguments={"x": 1})))
        self.assertIsNone(action_target(SimpleNamespace(arguments="click")))
        self.assertIsNone(action_target(None))


class StaticAgentFactory:
    def __init__(self, agent: FakeAgent) -> None:
        self.agent = agent
        self.calls = []

    def __call__(self, goal, stop_event, task):
        self.calls.append((goal, task.id))
        return self.agent


@unittest.skipIf(TestClient is None, "install requirements-bridge.txt to test HTTP adapter")
class ExecutionRoutingHttpTests(unittest.TestCase):
    def setUp(self):
        self.agent_factory = StaticAgentFactory(FakeAgent())
        self.cursor = CursorControlTasks(agent_factory=self.agent_factory)
        self.service = BridgeService.create(
            MockBackend(),
            lambda _task: ScriptedPlanner([Finish("done", no_artifacts_expected=True)]),
            token=TOKEN, cursor_control=self.cursor,
        )
        self.service.start()
        self.client = TestClient(create_app(self.service), base_url="http://127.0.0.1")
        self.headers = {"Authorization": f"Bearer {TOKEN}"}

    def tearDown(self):
        self.client.close()
        self.service.shutdown()

    def submit(self, payload, expected_status=201):
        response = self.client.post("/v1/tasks", headers=self.headers, json=payload)
        self.assertEqual(response.status_code, expected_status, response.text)
        return response.json()

    def task(self, task_id):
        response = self.client.get(f"/v1/tasks/{task_id}", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def wait_terminal(self, task_id, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            task = self.task(task_id)
            if task["status"] in TERMINAL_VALUES:
                return task
            time.sleep(0.01)
        self.fail(f"task {task_id} did not finish; last={task!r}")

    def test_default_submission_keeps_task_doing_behavior(self):
        created = self.submit({"goal": "finish"})

        self.assertEqual(created["execution_mode"], "task_doing")
        self.assertEqual(created["execution_environment"], "foreground")
        self.assertEqual(created["status"], TaskStatus.QUEUED.value)
        completed = self.wait_terminal(created["id"])
        self.assertEqual(completed["status"], TaskStatus.COMPLETED.value)
        self.assertEqual(self.task(created["id"])["execution_mode"], "task_doing")
        state = self.client.get("/v1/state", headers=self.headers).json()
        self.assertIn(created["id"], {task["id"] for task in state["tasks"]})
        self.assertEqual(self.agent_factory.calls, [])

    def test_explicit_task_doing_is_the_foreground_default(self):
        created = self.submit({"goal": "finish", "executionMode": "task_doing"})

        self.assertEqual(created["execution_environment"], "foreground")
        self.assertIn(created["id"], {task["id"] for task in
                                      self.client.get("/v1/state", headers=self.headers).json()["tasks"]})

    def test_background_mode_uses_manager_and_metadata_survives_polling(self):
        created = self.submit({"goal": "finish", "executionMode": "background_task"}, 202)

        self.assertEqual(created["execution_mode"], "background_task")
        self.assertEqual(created["execution_environment"], "background")
        final = self.wait_terminal(created["id"])
        self.assertEqual(final["status"], TaskStatus.COMPLETED.value)
        self.assertEqual(final["execution_mode"], "background_task")
        self.assertEqual(final["execution_environment"], "background")

    def test_cursor_control_runs_the_f16_handler_and_reports_desktop_metadata(self):
        created = self.submit({"goal": "open notepad", "executionMode": "cursor_control"}, 202)

        self.assertEqual(created["execution_mode"], "cursor_control")
        self.assertEqual(created["execution_environment"], "desktop")
        # The adapter starts the F16 thread immediately, so the submission may
        # already be running (or finished) by the time the response is built.
        self.assertIn(created["status"], {TaskStatus.QUEUED.value, TaskStatus.RUNNING.value,
                                          TaskStatus.COMPLETED.value})
        final = self.wait_terminal(created["id"])
        self.assertEqual(final["status"], TaskStatus.COMPLETED.value)
        self.assertEqual(final["result"]["summary"], "Desktop task finished.")
        self.assertEqual(final["execution_mode"], "cursor_control")
        self.assertEqual(self.agent_factory.calls[0][0], "open notepad")
        listed = self.client.get("/v1/tasks", headers=self.headers).json()["tasks"]
        self.assertIn(created["id"], {task["id"] for task in listed})

    def test_cursor_control_task_can_be_cancelled(self):
        started = threading.Event()
        cursor = CursorControlTasks(agent_factory=self._blocking_agent_factory(started))
        service = BridgeService.create(
            MockBackend(),
            lambda _task: ScriptedPlanner([Finish("done", no_artifacts_expected=True)]),
            token=TOKEN, cursor_control=cursor,
        )
        service.start()
        client = TestClient(create_app(service), base_url="http://127.0.0.1")
        headers = {"Authorization": f"Bearer {TOKEN}"}
        try:
            response = client.post("/v1/tasks", headers=headers,
                                   json={"goal": "hold", "executionMode": "cursor_control"})
            self.assertEqual(response.status_code, 202, response.text)
            task_id = response.json()["id"]
            self.assertTrue(started.wait(2), "cursor control agent did not start")
            cancelled = client.post(f"/v1/tasks/{task_id}/cancel", headers=headers)
            self.assertEqual(cancelled.status_code, 200, cancelled.text)
            self.assertTrue(cancelled.json()["accepted"])
            deadline = time.monotonic() + 5
            task = None
            while time.monotonic() < deadline:
                task = client.get(f"/v1/tasks/{task_id}", headers=headers).json()
                if task["status"] in TERMINAL_VALUES:
                    break
                time.sleep(0.01)
            self.assertEqual(task["status"], TaskStatus.CANCELLED.value)
            self.assertTrue(task["cancel_requested"])
        finally:
            client.close()
            service.shutdown()

    def test_invalid_mode_returns_bad_request(self):
        response = self.client.post("/v1/tasks", headers=self.headers,
                                    json={"goal": "finish", "executionMode": "teleport"})

        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()["error"]["code"], "BAD_REQUEST")

    def test_empty_goal_is_rejected_by_routing_layer(self):
        response = self.client.post("/v1/tasks", headers=self.headers,
                                    json={"goal": "   ", "executionMode": "background_task"})

        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(response.json()["error"]["code"], "INVALID_GOAL")

    @staticmethod
    def _blocking_agent_factory(started):
        def factory(goal, stop_event, task):
            class BlockingAgent:
                def run(self, _goal):
                    started.set()
                    stop_event.wait(5)
                    return SimpleNamespace(status="stopped", message="Stopped by the user.", turns=1)

                def stop(self):
                    pass

            return BlockingAgent()

        return factory


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
