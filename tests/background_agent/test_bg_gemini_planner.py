from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import helpers  # noqa: F401
from background_agent import (Action, ActionKind, BackgroundTaskManager, DefaultActionPolicy,
                              PolicyVerdict, TaskLimits, TaskStatus)
from background_agent.backends.mock import MockBackend
from background_agent.bridge.dev_server import DemoPlanner
from background_agent.errors import PlannerError
from background_agent.gemini_planner import GeminiPlanner, PLANNER_ACTIONS
from background_agent.planner import PlanContext


class FakeTextClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.prompt = None

    def generate_text(self, prompt, *, max_output_tokens=4096, timeout_seconds=45):
        self.prompt = prompt
        if self.error:
            raise self.error
        return self.response


def context(capabilities=PLANNER_ACTIONS, goal="make a report"):
    return PlanContext(goal, (), frozenset(capabilities), 20, 60.0)


class GeminiPlannerTests(unittest.TestCase):
    def test_valid_action_response_becomes_typed_action(self):
        client = FakeTextClient(json.dumps({
            "type": "action", "kind": "fs.write",
            "params": {"path": "report.txt", "content": "ready"},
        }))
        step = GeminiPlanner(client).next_step(context())
        self.assertEqual(step.kind, ActionKind.FS_WRITE)
        self.assertEqual(step.params["content"], "ready")
        self.assertIn("untrusted data", client.prompt)

    def test_valid_conversation_response_becomes_finish(self):
        client = FakeTextClient(json.dumps({
            "type": "finish", "summary": "Hello! I'm Ruby.",
            "claimed_outputs": [], "no_artifacts_expected": True,
        }))
        step = GeminiPlanner(client).next_step(context(goal="Hello Ruby"))
        self.assertEqual(step.summary, "Hello! I'm Ruby.")
        self.assertTrue(step.no_artifacts_expected)

    def test_malformed_and_ambiguous_responses_fail_closed(self):
        for response in ('not json', '{"type":"finish","type":"action"}'):
            with self.subTest(response=response), self.assertRaises(PlannerError):
                GeminiPlanner(FakeTextClient(response)).next_step(context())

    def test_provider_failure_is_useful_and_secret_is_redacted(self):
        client = FakeTextClient(error=RuntimeError("service unavailable GEMINI_API_KEY_VALUE"))
        with patch.dict("os.environ", {"GEMINI_API_KEY": "GEMINI_API_KEY_VALUE"}):
            with self.assertRaisesRegex(PlannerError, "Gemini request failed.*service unavailable") as caught:
                GeminiPlanner(client).next_step(context())
        self.assertNotIn("GEMINI_API_KEY_VALUE", str(caught.exception))

    def test_unsupported_process_gui_and_browser_actions_are_rejected(self):
        for kind in ("process.run", "process.shell", "browser.goto", "gui.launch_app"):
            response = json.dumps({"type": "action", "kind": kind, "params": {}})
            with self.subTest(kind=kind), self.assertRaises(PlannerError):
                GeminiPlanner(FakeTextClient(response)).next_step(context(capabilities=ActionKind))

    def test_demo_planner_remains_available_for_development(self):
        step = DemoPlanner("demo task").next_step(context())
        self.assertEqual(step.kind, ActionKind.FS_WRITE)

    def test_delete_decision_still_goes_through_policy_and_confirmation(self):
        backend = MockBackend()
        client = FakeTextClient()
        responses = iter([
            json.dumps({"type": "action", "kind": "fs.delete", "params": {"path": "victim.txt"}}),
            json.dumps({"type": "finish", "summary": "Deletion was not approved; no change was made.",
                        "claimed_outputs": [], "no_artifacts_expected": True}),
        ])
        client.generate_text = lambda *_a, **_k: next(responses)
        seen = []
        manager = BackgroundTaskManager(
            backend, lambda _task: GeminiPlanner(client), policy=DefaultActionPolicy(),
            confirmation_handler=lambda request, _cancel: seen.append(request) or False,
            default_limits=TaskLimits(max_runtime_seconds=5, cancel_grace_seconds=0.2),
        )
        manager.start()
        try:
            task = manager.submit("remove victim.txt")
            self.assertTrue(task.wait(3))
            self.assertEqual(task.status, TaskStatus.COMPLETED)
            self.assertEqual(len(seen), 1)
            self.assertEqual(seen[0].kind, ActionKind.FS_DELETE)
            self.assertNotIn("exec:fs.delete", backend.events)
            self.assertIs(DefaultActionPolicy().evaluate(
                Action(ActionKind.FS_DELETE, {"path": "x"}), task
            ).verdict, PolicyVerdict.CONFIRM)
        finally:
            manager.shutdown()


if __name__ == "__main__":
    unittest.main()
