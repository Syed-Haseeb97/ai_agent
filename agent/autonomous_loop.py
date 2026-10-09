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
        on_action_start: Callable[[Any], None] | None = None,
        on_action_end: Callable[[Any], None] | None = None,
    ):
        if max_turns < 1:
            raise ValueError("max_turns must be at least 1")
        if max_runtime_seconds < 1:
            raise ValueError("max_runtime_seconds must be at least 1 second")
        self.client = client if client is not None else ComputerUseClient()
        self.executor = executor if executor is not None else WindowsComputerExecutor()
        self.policy = policy if policy is not None else AutonomousPolicy()
        self.capture = capture
        self.max_turns = max_turns
        self.max_runtime_seconds = max_runtime_seconds
        self.stop_event = stop_event if stop_event is not None else threading.Event()
        self.on_action_start = on_action_start
        self.on_action_end = on_action_end

    @staticmethod
    def _notify_action(callback: Callable[[Any], None] | None, action: Any) -> None:
        """Visual hooks must never break or delay the actual desktop action."""
        if callback is not None:
            try:
                callback(action)
            except Exception:
                pass

    def stop(self) -> None:
        self.stop_event.set()

    def run(self, goal: str) -> AgentRunResult:
        goal = goal.strip()
        if not goal:
            return AgentRunResult("invalid", 0, "No autonomous goal was supplied.")
        if self.stop_event.is_set():
            return AgentRunResult("stopped", 0, "Stopped by the user.")

        started = time.monotonic()
        try:
            screenshot, _ = self.capture()
            if self.stop_event.is_set():
                return AgentRunResult("stopped", 0, "Stopped by the user.")
            interaction = self.client.start(goal, screenshot, self.policy)

            for turn in range(1, self.max_turns + 1):
                if self.stop_event.is_set():
                    return AgentRunResult("stopped", turn - 1, "Stopped by the user.")
                if time.monotonic() - started >= self.max_runtime_seconds:
                    return AgentRunResult("timeout", turn - 1, "Maximum autonomous runtime reached.")

                actions = extract_actions(interaction)
                if not actions:
                    return AgentRunResult(
                        "completed",
                        turn,
                        extract_text(interaction) or "The agent finished without further UI actions.",
                    )

                executions = []
                for action in actions:
                    if self.stop_event.is_set():
                        return AgentRunResult("stopped", turn - 1, "Stopped by the user.")

                    decision = self.policy.check_action(action.name, action.arguments)
                    if not decision.allowed:
                        status = "confirmation_required" if "confirmation" in decision.reason.casefold() or "require_confirmation" in decision.reason.casefold() else "blocked"
                        return AgentRunResult(status, turn, decision.reason)

                    self._notify_action(self.on_action_start, action)
                    try:
                        execution = self.executor.execute(action)
                    finally:
                        self._notify_action(self.on_action_end, action)
                    executions.append(execution)
                    if execution.result.get("error"):
                        return AgentRunResult(
                            "action_error",
                            turn,
                            f"Action {action.name!r} failed; stopped to avoid continuing from an unknown screen state: {execution.result['error']}",
                        )
                    if self.stop_event.is_set():
                        return AgentRunResult("stopped", turn, "Stopped by the user.")

                if time.monotonic() - started >= self.max_runtime_seconds:
                    return AgentRunResult("timeout", turn, "Maximum autonomous runtime reached.")
                screenshot, _ = self.capture()
                if self.stop_event.is_set():
                    return AgentRunResult("stopped", turn, "Stopped by the user.")
                interaction = self.client.continue_interaction(interaction.id, function_results(executions, screenshot))

            return AgentRunResult("turn_limit", self.max_turns, "Maximum autonomous turn count reached.")
        except Exception as exc:
            return AgentRunResult("error", 0, f"Autonomous run failed safely: {type(exc).__name__}: {str(exc)[:240]}")
