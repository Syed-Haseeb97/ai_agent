"""Safety policy for Ruby's autonomous computer-use mode."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str = ""


# Keep this in sync with WindowsComputerExecutor. Unknown tool names must never
# reach the desktop executor just because the model supplied them.
ALLOWED_ACTIONS = frozenset({
    "click", "click_at", "double_click", "triple_click", "middle_click",
    "right_click", "move", "mouse_down", "mouse_up", "type", "type_text_at",
    "press_key", "key_down", "key_up", "hotkey", "drag_and_drop", "drag",
    "scroll", "long_press", "wait", "take_screenshot",
})

BLOCKED_INTENT_TERMS = (
    "captcha", "terms of service", "privacy policy", "cookie consent",
    "accept terms", "purchase", "buy", "checkout", "payment", "transfer money",
    "send email", "send message", "post", "publish", "delete file", "delete folder",
    "format drive", "password", "passcode", "one-time code", "otp", "2fa", "mfa",
    "bank account", "credit card", "social security", "government record",
)


class AutonomousPolicy:
    """Allow known routine UI actions, but stop before consequential actions."""

    def check_action(self, name: str, arguments: dict[str, Any]) -> PolicyDecision:
        if not isinstance(arguments, dict):
            return PolicyDecision(False, "Blocked: action arguments must be an object.")

        if name not in ALLOWED_ACTIONS:
            return PolicyDecision(False, f"Blocked: unsupported Computer Use action {name!r}.")

        safety = arguments.get("safety_decision")
        if safety is not None:
            if not isinstance(safety, dict):
                return PolicyDecision(False, "Blocked: malformed Computer Use safety decision.")
            decision = str(safety.get("decision", "")).strip().lower()
            if decision == "require_confirmation":
                return PolicyDecision(
                    False,
                    str(safety.get("explanation") or "Computer Use requires user confirmation."),
                )
            if decision == "blocked":
                return PolicyDecision(
                    False,
                    str(safety.get("explanation") or "Computer Use safety system blocked this action."),
                )
            if decision not in {"allow", "allowed", "regular"}:
                return PolicyDecision(
                    False,
                    f"Blocked: unrecognized or missing Computer Use safety decision {decision!r}.",
                )

        intent = str(arguments.get("intent", "")).casefold()
        text = f"{name} {intent}"
        for term in BLOCKED_INTENT_TERMS:
            if term in text:
                return PolicyDecision(False, f"Blocked by autonomous safety policy: {term}")
        return PolicyDecision(True)

    def system_instruction(self) -> str:
        return (
            "You are Ruby running in autonomous desktop mode. Continue the user's stated task "
            "without repeatedly asking for routine confirmation. You may click, type, scroll, "
            "wait, and use ordinary UI controls needed to complete the task. Treat routine "
            "in-app permission prompts as part of the requested workflow only when clearly "
            "required to continue and not involving security, privacy, legal consent, account access, "
            "or consequential changes. Never accept Terms of Service, privacy/cookie consent, CAPTCHAs, "
            "payments, purchases, money transfers, account creation/login, OTP/2FA, password entry, "
            "sending messages/emails, publishing, or destructive file/system changes. If the screen "
            "requires one of those, stop and yield control instead of guessing. If you are unsure, stop."
        )
