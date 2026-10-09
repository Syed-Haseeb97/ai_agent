import threading
import unittest
from unittest.mock import patch

from agent.autonomous_loop import AutonomousAgent
from agent.computer_use import ActionExecution, extract_actions
from agent.policy import AutonomousPolicy


class FakeStep:
    def __init__(self, typ, name=None, arguments=None, call_id="1", content=None):
        self.type = typ
        self.name = name
        self.arguments = arguments or {}
        self.id = call_id
        self.content = content or []


class FakeInteraction:
    def __init__(self, steps, ident="i1"):
        self.steps = steps
        self.id = ident


class FakeClient:
    def __init__(self):
        self.calls = 0
        self.inputs = []
        self.os_contexts = []

    def start(self, goal, screenshot, policy, os_context=None):
        self.calls += 1
        self.os_contexts.append(os_context)
        return FakeInteraction([
            FakeStep("function_call", "click", {
                "x": 500, "y": 500, "intent": "Click routine UI control"
            }, "c1")
        ])

    def continue_interaction(self, interaction_id, function_results):
        self.calls += 1
        self.inputs.append(function_results)
        return FakeInteraction([
            FakeStep("model_output", content=[{"type": "text", "text": "done"}])
        ], "i2")


class FakeExecutor:
    def __init__(self, result=None, on_execute=None):
        self.actions = []
        self.result = result if result is not None else {"ok": True}
        self.on_execute = on_execute

    def execute(self, action):
        self.actions.append(action)
        if self.on_execute:
            self.on_execute()
        return ActionExecution(action.name, action.call_id, self.result)


class AutonomousAgentTests(unittest.TestCase):
    def test_extracts_modern_function_call(self):
        action = extract_actions(FakeInteraction([
            FakeStep("function_call", "click", {"x": 1, "y": 2, "intent": "click"})
        ]))[0]
        self.assertEqual(action.name, "click")
        self.assertEqual(action.arguments["x"], 1)

    def test_policy_allows_routine_action(self):
        self.assertTrue(AutonomousPolicy().check_action("click", {"intent": "Click routine UI control"}).allowed)

    def test_policy_blocks_consequential_intent(self):
        decision = AutonomousPolicy().check_action("click", {"intent": "Click Purchase"})
        self.assertFalse(decision.allowed)

    def test_policy_blocks_confirmation_decision(self):
        decision = AutonomousPolicy().check_action("click", {"safety_decision": {"decision": "require_confirmation"}})
        self.assertFalse(decision.allowed)

    def test_policy_fails_closed_on_malformed_safety_decision(self):
        for value in ("allow", None, {}, {"decision": "future_unknown_value"}):
            with self.subTest(value=value):
                decision = AutonomousPolicy().check_action("click", {"safety_decision": value})
                self.assertFalse(decision.allowed)

    def test_policy_blocks_unknown_action_before_executor(self):
        decision = AutonomousPolicy().check_action("launch_shell", {"intent": "routine"})
        self.assertFalse(decision.allowed)

    def test_invalid_limits_are_rejected(self):
        with self.assertRaises(ValueError):
            AutonomousAgent(client=FakeClient(), executor=FakeExecutor(), max_turns=0)
        with self.assertRaises(ValueError):
            AutonomousAgent(client=FakeClient(), executor=FakeExecutor(), max_runtime_seconds=0)
        with self.assertRaises(ValueError):
            AutonomousAgent(client=FakeClient(), executor=FakeExecutor(), max_file_verification_retries=-1)

    def test_stop_event_halts_before_capture_or_api(self):
        stop = threading.Event()
        stop.set()
        client, executor = FakeClient(), FakeExecutor()
        agent = AutonomousAgent(
            client=client, executor=executor,
            capture=lambda: self.fail("capture should not run"), stop_event=stop,
        )
        result = agent.run("anything")
        self.assertEqual(result.status, "stopped")
        self.assertEqual(client.calls, 0)
        self.assertEqual(executor.actions, [])

    def test_stop_requested_during_action_prevents_next_api_call(self):
        stop = threading.Event()
        client = FakeClient()
        executor = FakeExecutor(on_execute=stop.set)
        agent = AutonomousAgent(
            client=client, executor=executor,
            capture=lambda: (b"screen", (100, 100)), stop_event=stop,
        )
        result = agent.run("Finish the routine desktop task")
        self.assertEqual(result.status, "stopped")
        self.assertEqual(client.calls, 1)

    def test_loop_executes_then_finishes(self):
        client, executor = FakeClient(), FakeExecutor()
        agent = AutonomousAgent(
            client=client, executor=executor,
            capture=lambda: (b"screen", (100, 100)), max_turns=3,
        )
        result = agent.run("Finish the routine desktop task")
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(executor.actions), 1)
        self.assertEqual(client.calls, 2)
        self.assertIn("Native OS context", str(client.inputs[0]))

    def test_expected_output_paths_are_injected_into_initial_os_context(self):
        client = FakeClient()
        executor = FakeExecutor()
        expected_path = "C:/Users/test/Documents/ruby_test.txt"
        context = {"running_processes": [], "active_window_title": "Notepad",
                   "filesystem_status": {expected_path: {"exists": False, "is_file": False}}}
        with patch("agent.autonomous_loop.goal_file_paths", return_value=[expected_path]), patch(
            "agent.autonomous_loop.collect_os_context", return_value=context
        ):
            agent = AutonomousAgent(
                client=client, executor=executor,
                capture=lambda: (b"screen", (100, 100)), max_turns=3,
            )
            result = agent.run("Complete the routine desktop task")
        self.assertEqual(result.status, "completed")
        self.assertEqual(client.os_contexts[0]["filesystem_status"][expected_path]["exists"], False)

    def test_action_error_stops_loop(self):
        client, executor = FakeClient(), FakeExecutor({"error": "click failed"})
        agent = AutonomousAgent(
            client=client, executor=executor,
            capture=lambda: (b"screen", (100, 100)), max_turns=3,
        )
        result = agent.run("Finish the routine desktop task")
        self.assertEqual(result.status, "action_error")
        self.assertEqual(client.calls, 1)


if __name__ == "__main__":
    unittest.main()
