"""Long-running autonomous Gemini Computer Use loop for Ruby."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from agent.computer_use import ComputerUseClient, WindowsComputerExecutor, extract_actions, extract_text, function_results
from agent.policy import AutonomousPolicy
from vision.capture import capture_primary_screen


@dataclass(frozen=True)
class AgentRunResult:
    status: str
    turns: int
    message: str


class AutonomousAgent:
    """Run one objective continuously until completion, a safety stop, or a limit."""

    def __init__(
        self,
        client: Any | None = None,
        executor: Any | None = None,
        policy: AutonomousPolicy | None = None,
        capture: Callable[[], tuple[bytes, tuple[int, int]]] = capture_primary_screen,
        max_turns: int = 120,
        max_runtime_seconds: int = 4 * 60 * 60,
        stop_event: threading.Event | None = None,
    ):
        self.client = client or ComputerUseClient()
        self.executor = executor or WindowsComputerExecutor()
        self.policy = policy or AutonomousPolicy()
        self.capture = capture
        self.max_turns = max_turns
        self.max_runtime_seconds = max_runtime_seconds
        self.stop_event = stop_event or threading.Event()

    def stop(self) -> None:
        self.stop_event.set()

    def run(self, goal: str) -> AgentRunResult:
        goal = goal.strip()
        if not goal:
            return AgentRunResult("invalid", 0, "No autonomous goal was supplied.")
        started = time.monotonic()
        screenshot, _ = self.capture()
        interaction = self.client.start(goal, screenshot, self.policy)

        for turn in range(1, self.max_turns + 1):
            if self.stop_event.is_set():
                return AgentRunResult("stopped", turn - 1, "Stopped by the user.")
            if time.monotonic() - started >= self.max_runtime_seconds:
                return AgentRunResult("timeout", turn - 1, "Maximum autonomous runtime reached.")

            actions = extract_actions(interaction)
            if not actions:
                return AgentRunResult("completed", turn, extract_text(interaction) or "The agent finished without further UI actions.")

            executions = []
            for action in actions:
                decision = self.policy.check_action(action.name, action.arguments)
                safety = action.arguments.get("safety_decision") or {}
                if not decision.allowed:
                    return AgentRunResult("blocked", turn, decision.reason)
                if str(safety.get("decision", "")).lower() == "require_confirmation":
                    return AgentRunResult("confirmation_required", turn, str(safety.get("explanation", "Gemini requires user confirmation.")))
                if str(safety.get("decision", "")).lower() == "blocked":
                    return AgentRunResult("blocked", turn, str(safety.get("explanation", "Gemini blocked the action.")))
                executions.append(self.executor.execute(action))
                if self.stop_event.is_set():
                    return AgentRunResult("stopped", turn, "Stopped by the user.")

            screenshot, _ = self.capture()
            interaction = self.client.continue_interaction(interaction.id, function_results(executions, screenshot))

        return AgentRunResult("turn_limit", self.max_turns, "Maximum autonomous turn count reached.")
