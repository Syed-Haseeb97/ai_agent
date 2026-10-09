"""Long-running autonomous Gemini Computer Use loop for Ruby."""
from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from agent.computer_use import ComputerUseClient, WindowsComputerExecutor, extract_actions, extract_text, function_results
from agent.policy import AutonomousPolicy
from agent.verifier import collect_os_context, verify_goal_app_launch, verify_goal_file_outputs
from vision.capture import capture_primary_screen


@dataclass(frozen=True)
class AgentRunResult:
    status: str
    turns: int
    message: str


class AutonomousAgent:
    """Run one objective until verified completion, a safety stop, or a hard limit."""

    def __init__(
        self,
        client: Any | None = None,
        executor: Any | None = None,
        policy: AutonomousPolicy | None = None,
        capture: Callable[[], tuple[bytes, tuple[int, int]]] = capture_primary_screen,
        max_turns: int = 120,
        max_runtime_seconds: int = 4 * 60 * 60,
        stop_event: threading.Event | None = None,
        max_file_verification_retries: int = 3,
    ):
        if max_turns < 1:
            raise ValueError("max_turns must be at least 1")
        if max_runtime_seconds < 1:
            raise ValueError("max_runtime_seconds must be at least 1 second")
        if max_file_verification_retries < 0:
            raise ValueError("max_file_verification_retries cannot be negative")

        self.stop_event = stop_event if stop_event is not None else threading.Event()
        self.client = client if client is not None else ComputerUseClient()
        self.executor = executor if executor is not None else WindowsComputerExecutor(stop_event=self.stop_event)
        self.policy = policy if policy is not None else AutonomousPolicy()
        self.capture = capture
        self.max_turns = max_turns
        self.max_runtime_seconds = max_runtime_seconds
        self.max_file_verification_retries = max_file_verification_retries

    def stop(self) -> None:
        """Request a cooperative stop; the loop checks this between actions."""
        self.stop_event.set()

    def run(self, goal: str) -> AgentRunResult:
        goal = goal.strip()
        if not goal:
            return AgentRunResult("invalid", 0, "No autonomous goal was supplied.")
        if self.stop_event.is_set():
            return AgentRunResult("stopped", 0, "Stopped by the user.")

        started = time.monotonic()
        verification_failures = 0
        previous_turn_signatures: set[str] = set()
        previous_turn_screen_hash = ""
        try:
            screenshot, _ = self.capture()
            if self.stop_event.is_set():
                return AgentRunResult("stopped", 0, "Stopped by the user.")
            os_context = collect_os_context()
            interaction = self.client.start(goal, screenshot, self.policy, os_context)

            for turn in range(1, self.max_turns + 1):
                if self.stop_event.is_set():
                    return AgentRunResult("stopped", turn - 1, "Stopped by the user.")
                if time.monotonic() - started >= self.max_runtime_seconds:
                    return AgentRunResult("timeout", turn - 1, "Maximum autonomous runtime reached.")

                actions = extract_actions(interaction)
                if not actions:
                    verification = verify_goal_file_outputs(goal)
                    if verification is None:
                        verification = verify_goal_app_launch(goal)
                    if verification is None or verification[0]:
                        message = extract_text(interaction) or "The agent finished without further UI actions."
                        if verification is not None:
                            message = f"{message} {verification[1]}".strip()
                        return AgentRunResult("completed", turn, message)

                    if verification_failures >= self.max_file_verification_retries:
                        return AgentRunResult("verification_failed", turn, verification[1])

                    verification_failures += 1
                    feedback = (
                        f"{verification[1]} Do not claim completion. Continue the task and correct the "
                        "problem if it is safe to do so. After making changes, allow native verification "
                        "to run again. This is verification retry "
                        f"{verification_failures} of {self.max_file_verification_retries}."
                    )
                    interaction = self.client.continue_interaction(
                        interaction.id, [{"type": "text", "text": feedback}]
                    )
                    continue

                screen_hash = hashlib.sha256(screenshot).hexdigest()
                current_signatures: set[str] = set()
                executions = []
                for action in actions:
                    signature = json.dumps(
                        {"name": action.name, "arguments": action.arguments},
                        sort_keys=True, separators=(",", ":"), default=str,
                    )
                    current_signatures.add(signature)
                    if signature in previous_turn_signatures and screen_hash == previous_turn_screen_hash:
                        return AgentRunResult(
                            "stuck", turn - 1,
                            f"Stopped safely: repeated action {action.name!r} was proposed "
                            "again without a visible screen change.",
                        )

                    if self.stop_event.is_set():
                        return AgentRunResult("stopped", turn - 1, "Stopped by the user.")
                    decision = self.policy.check_action(action.name, action.arguments)
                    if not decision.allowed:
                        status = (
                            "confirmation_required"
                            if "confirmation" in decision.reason.casefold()
                            or "require_confirmation" in decision.reason.casefold()
                            else "blocked"
                        )
                        return AgentRunResult(status, turn, decision.reason)

                    execution = self.executor.execute(action)
                    if self.stop_event.is_set():
                        return AgentRunResult("stopped", turn, "Stopped by the user.")
                    if execution.result.get("error"):
                        return AgentRunResult(
                            "action_error", turn,
                            f"Action {action.name!r} failed; stopped to avoid continuing "
                            f"from an unknown screen state: {execution.result['error']}",
                        )
                    executions.append(execution)

                if time.monotonic() - started >= self.max_runtime_seconds:
                    return AgentRunResult("timeout", turn, "Maximum autonomous runtime reached.")
                previous_turn_signatures = current_signatures
                previous_turn_screen_hash = screen_hash
                screenshot, _ = self.capture()
                if self.stop_event.is_set():
                    return AgentRunResult("stopped", turn, "Stopped by the user.")
                os_context = collect_os_context()
                interaction = self.client.continue_interaction(
                    interaction.id, function_results(executions, screenshot, os_context)
                )

            return AgentRunResult("turn_limit", self.max_turns, "Maximum autonomous turn count reached.")
        except Exception as exc:
            return AgentRunResult("error", 0, f"Autonomous run failed safely: {type(exc).__name__}: {str(exc)[:240]}")
