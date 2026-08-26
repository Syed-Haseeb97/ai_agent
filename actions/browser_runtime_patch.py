"""Deprecated compatibility shim.

Previously this module monkey-patched BrowserAgent/BrowserActions at import
time. That approach fought the core implementation and made debugging hard.

All functionality now lives in:
  - actions.browser_actions.BrowserActions  (persistent worker-thread Playwright)
  - actions.browser_agent.BrowserAgent      (generic planner)

Importing this module is a no-op kept only so older code paths do not crash.
"""
from __future__ import annotations

# Intentionally empty.
