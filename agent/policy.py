"""Safety policy for Ruby's autonomous computer-use mode."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str = ""


BLOCKED_INTENT_TERMS = (
    "captcha", "terms of service", "privacy policy", "cookie consent",
    "accept terms", "purchase", "buy", "checkout", "payment", "transfer money",
    "send email", "send message", "post", "publish", "delete file", "delete folder",
    "format drive", "password", "passcode", "one-time code", "otp", "2fa", "mfa",
    "bank account", "credit card", "social security", "government record",
)


class AutonomousPolicy:
    """Allow routine UI automation but stop before consequential actions."""

    def check_action(self, name: str, arguments: dict) -> PolicyDecision:
        intent = str(arguments.get("intent", "")).lower()
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
            "in-app permission prompts as part of the requested workflow when they are clearly "
            "required to continue. Never accept Terms of Service, privacy/cookie consent, CAPTCHAs, "
            "payments, purchases, money transfers, account creation/login, OTP/2FA, password entry, "
            "sending messages/emails, publishing, or destructive file/system changes. If the screen "
            "requires one of those, stop and yield control instead of guessing. If you are unsure, stop."
        )
