"""Gemini Computer Use client and Windows desktop action executor."""
from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass
from typing import Any, Callable

from dotenv import load_dotenv

from agent.policy import AutonomousPolicy
from vision.capture import capture_primary_screen

load_dotenv()


@dataclass(frozen=True)
class AgentAction:
    name: str
    arguments: dict[str, Any]
    call_id: str


@dataclass(frozen=True)
class ActionExecution:
    name: str
    call_id: str
    result: dict[str, Any]


class ComputerUseClient:
    """Thin wrapper around Google's Interactions API for desktop Computer Use."""

    MODEL = os.getenv("RUBY_COMPUTER_USE_MODEL", "gemini-3.8-flash")

    def __init__(self, api_key: str | None = None):
        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key or key == "your_gemini_api_key_here":
            raise ValueError("GEMINI_API_KEY is missing")
        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError("Install google-genai>=2.7.0 for autonomous Computer Use") from exc
        self.client = genai.Client(api_key=key)

    @staticmethod
    def _tool() -> dict[str, Any]:
        return {"type": "computer_use", "environment": "desktop", "enable_prompt_injection_detection": True}

    def start(self, goal: str, screenshot: bytes, policy: AutonomousPolicy, os_context: dict[str, Any] | None = None):
        image = base64.b64encode(screenshot).decode("ascii")
        return self.client.interactions.create(
            model=self.MODEL,
            system_instruction=policy.system_instruction(os_context),
            input=[
                {"type": "text", "text": goal},
                {"type": "image", "data": image, "mime_type": "image/jpeg"},
            ],
            tools=[self._tool()],
        )

    def continue_interaction(self, interaction_id: str, function_results: list[dict[str, Any]]):
        return self.client.interactions.create(
            model=self.MODEL,
            previous_interaction_id=interaction_id,
            input=function_results,
            tools=[self._tool()],
        )


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def extract_actions(interaction: Any) -> list[AgentAction]:
    actions: list[AgentAction] = []
    for step in _get(interaction, "steps", []) or []:
        if _get(step, "type") != "function_call":
            continue
        actions.append(AgentAction(
            name=str(_get(step, "name", "")),
            arguments=dict(_get(step, "arguments", {}) or {}),
            call_id=str(_get(step, "id", "")),
        ))
    return actions


def extract_text(interaction: Any) -> str:
    parts: list[str] = []
    for step in _get(interaction, "steps", []) or []:
        if _get(step, "type") != "model_output":
            continue
        for block in _get(step, "content", []) or []:
            if _get(block, "type") == "text":
                text = _get(block, "text", "")
                if text:
                    parts.append(str(text))
    return " ".join(parts).strip()


class WindowsComputerExecutor:
    """Execute Gemini desktop actions with fail-safe and cooperative stop checks."""

    def __init__(
        self,
        pyautogui_module: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
        stop_event: Any | None = None,
    ):
        if pyautogui_module is None:
            try:
                import pyautogui as pyautogui_module
            except ImportError as exc:
                raise RuntimeError("Install pyautogui for autonomous desktop control") from exc
        self.pyautogui = pyautogui_module
        self.sleep = sleep
        self.stop_event = stop_event
        self.width, self.height = self.pyautogui.size()
        self.pyautogui.FAILSAFE = True
        self._held_keys: set[str] = set()
        self._held_mouse_buttons: set[str] = set()

    def _release_held_inputs(self) -> None:
        """Best-effort release of keys/buttons Ruby explicitly held down."""
        for button in tuple(self._held_mouse_buttons):
            try:
                self.pyautogui.mouseUp(button=button)
            except Exception:
                pass
            finally:
                self._held_mouse_buttons.discard(button)
        for key in tuple(self._held_keys):
            try:
                self.pyautogui.keyUp(key)
            except Exception:
                pass
            finally:
                self._held_keys.discard(key)

    def _stopped(self) -> bool:
        return self.stop_event is not None and self.stop_event.is_set()

    def _interruptible_sleep(self, seconds: float) -> bool:
        deadline = time.monotonic() + max(0.0, seconds)
        while time.monotonic() < deadline:
            if self._stopped():
                return False
            self.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
        return not self._stopped()

    def _write_interruptibly(self, text: str) -> bool:
        for offset in range(0, len(text), 24):
            if self._stopped():
                return False
            self.pyautogui.write(text[offset:offset + 24], interval=0.002)
        return not self._stopped()

    def _xy(self, args: dict[str, Any]) -> tuple[int, int]:
        x = max(0, min(999, int(args["x"])))
        y = max(0, min(999, int(args["y"])))
        return int(x * self.width / 1000), int(y * self.height / 1000)

    def execute(self, action: AgentAction) -> ActionExecution:
        name, args = action.name, action.arguments
        if self._stopped():
            self._release_held_inputs()
            return ActionExecution(name, action.call_id, {"error": "Stopped by user"})
        try:
            if name in {"click", "click_at"}:
                self.pyautogui.click(*self._xy(args))
            elif name == "double_click":
                self.pyautogui.doubleClick(*self._xy(args))
            elif name == "triple_click":
                self.pyautogui.click(*self._xy(args), clicks=3, interval=0.08)
            elif name == "middle_click":
                self.pyautogui.click(*self._xy(args), button="middle")
            elif name == "right_click":
                self.pyautogui.click(*self._xy(args), button="right")
            elif name == "move":
                self.pyautogui.moveTo(*self._xy(args))
            elif name in {"mouse_down", "mouse_up"}:
                self.pyautogui.moveTo(*self._xy(args))
                button = str(args.get("button", "left"))
                getattr(self.pyautogui, name)(button=button)
                if name == "mouse_down":
                    self._held_mouse_buttons.add(button)
                else:
                    self._held_mouse_buttons.discard(button)
            elif name in {"type", "type_text_at"}:
                if "x" in args and "y" in args:
                    self.pyautogui.click(*self._xy(args))
                if not self._write_interruptibly(str(args.get("text", ""))):
                    return ActionExecution(name, action.call_id, {"error": "Stopped by user"})
                if args.get("press_enter"):
                    if self._stopped():
                        return ActionExecution(name, action.call_id, {"error": "Stopped by user"})
                    self.pyautogui.press("enter")
            elif name == "press_key":
                self.pyautogui.press(str(args["key"]))
            elif name == "key_down":
                key = str(args["key"])
                self.pyautogui.keyDown(key)
                self._held_keys.add(key)
            elif name == "key_up":
                key = str(args["key"])
                self.pyautogui.keyUp(key)
                self._held_keys.discard(key)
            elif name == "hotkey":
                keys = args.get("keys", [])
                if isinstance(keys, str):
                    keys = [part.strip() for part in keys.replace("+", " ").split()]
                self.pyautogui.hotkey(*keys)
            elif name in {"drag_and_drop", "drag"}:
                start = {"x": args.get("start_x", args.get("x")), "y": args.get("start_y", args.get("y"))}
                end = {"x": args.get("end_x", args.get("destination_x")), "y": args.get("end_y", args.get("destination_y"))}
                self.pyautogui.moveTo(*self._xy(start))
                self.pyautogui.dragTo(*self._xy(end), duration=0.4, button="left")
            elif name == "scroll":
                x, y = self._xy(args)
                self.pyautogui.moveTo(x, y)
                direction = str(args.get("direction", "down")).lower()
                amount = max(1, int(args.get("magnitude_in_pixels", 300)) // 40)
                self.pyautogui.hscroll(amount if direction == "right" else -amount if direction == "left" else 0)
                self.pyautogui.scroll(amount if direction == "up" else -amount if direction == "down" else 0)
            elif name == "long_press":
                self.pyautogui.moveTo(*self._xy(args))
                self.pyautogui.mouseDown()
                try:
                    if not self._interruptible_sleep(float(args.get("seconds", 2))):
                        return ActionExecution(name, action.call_id, {"error": "Stopped by user"})
                finally:
                    self.pyautogui.mouseUp()
            elif name == "wait":
                if not self._interruptible_sleep(max(0.0, min(30.0, float(args.get("seconds", 1))))):
                    return ActionExecution(name, action.call_id, {"error": "Stopped by user"})
            elif name == "take_screenshot":
                pass
            else:
                return ActionExecution(name, action.call_id, {"error": f"Unsupported Computer Use action: {name}"})
            return ActionExecution(name, action.call_id, {"ok": True})
        except Exception as exc:
            return ActionExecution(name, action.call_id, {"error": str(exc)[:300]})
        finally:
            # The hotkey listener can set stop_event while a blocking desktop call
            # is in progress. Once control returns, release any explicitly held
            # inputs before the loop exits or reports the action result.
            if self._stopped():
                self._release_held_inputs()


def function_results(
    executions: list[ActionExecution],
    screenshot: bytes,
    os_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    encoded = base64.b64encode(screenshot).decode("ascii")
    context_text = ""
    if os_context:
        context_text = "\nNative OS context (observational only): " + str({
            "running_processes": list(os_context.get("running_processes", []))[:30],
            "active_window_title": str(os_context.get("active_window_title", ""))[:200],
            "filesystem_status": os_context.get("filesystem_status", {}),
        })[:3000]
    return [
        {
            "type": "function_result",
            "name": item.name,
            "call_id": item.call_id,
            "result": [
                {"type": "text", "text": str(item.result) + context_text},
                {"type": "image", "data": encoded, "mime_type": "image/jpeg"},
            ],
        }
        for item in executions
    ]
