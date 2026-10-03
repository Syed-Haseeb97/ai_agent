import threading
import unittest

from agent.autonomous_loop import AutonomousAgent
from agent.computer_use import AgentAction, ActionExecution, extract_actions, extract_text
from agent.policy import AutonomousPolicy


class FakeStep:
    def __init__(self, typ, name=None, arguments=None, call_id="1", content=None):
        self.type = typ; self.name = name; self.arguments = arguments or {}; self.id = call_id; self.content = content or []


class FakeInteraction:
    def __init__(self, steps, ident="i1"):
        self.steps = steps; self.id = ident


class FakeClient:
    def __init__(self): self.calls = 0
    def start(self, goal, screenshot, policy):
        self.calls += 1
        return FakeInteraction([FakeStep("function_call", "click", {"x": 500, "y": 500, "intent": "Click routine permission Allow"}, "c1")])
    def continue_interaction(self, interaction_id, function_results):
        self.calls += 1
        return FakeInteraction([FakeStep("model_output", content=[{"type":"text", "text":"done"}])], "i2")


class FakeExecutor:
    def __init__(self): self.actions=[]
    def execute(self, action): self.actions.append(action); return ActionExecution(action.name, action.call_id, {"ok":True})


class AutonomousAgentTests(unittest.TestCase):
    def test_extracts_modern_function_call(self):
        action = extract_actions(FakeInteraction([FakeStep("function_call", "click", {"x": 1, "y": 2, "intent": "click"})]))[0]
        self.assertEqual(action.name, "click")
        self.assertEqual(action.arguments["x"], 1)

    def test_policy_allows_routine_permission(self):
        self.assertTrue(AutonomousPolicy().check_action("click", {"intent":"Click routine permission Allow"}).allowed)

    def test_policy_blocks_consequential_intent(self):
        decision = AutonomousPolicy().check_action("click", {"intent":"Click Purchase"})
        self.assertFalse(decision.allowed)

    def test_loop_executes_then_finishes(self):
        client, executor = FakeClient(), FakeExecutor()
        agent = AutonomousAgent(client=client, executor=executor, capture=lambda:(b"screen",(100,100)), max_turns=3)
        result = agent.run("Finish the routine desktop task")
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(executor.actions), 1)
        self.assertEqual(client.calls, 2)

    def test_stop_event_halts_before_execution(self):
        stop = threading.Event(); stop.set()
        agent = AutonomousAgent(client=FakeClient(), executor=FakeExecutor(), capture=lambda:(b"screen",(100,100)), stop_event=stop)
        result = agent.run("anything")
        self.assertEqual(result.status, "stopped")


if __name__ == "__main__":
    unittest.main()
