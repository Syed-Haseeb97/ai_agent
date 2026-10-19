# Ruby Background Agent (core package)

Lets Ruby work on a long task **in a separate execution environment** while you keep using
your computer. The Electron shell consumes this package through the authenticated localhost bridge.

> **The guarantee this package is built around:** selecting *Background Task* must never mean
> Ruby moves your mouse, types on your keyboard, or takes focus on your real desktop.
> The only backend shipped here (`LocalToolBackend`) has **no mouse/keyboard/screen-control
> capability at all**. GUI work returns `GUI_ISOLATION_REQUIRED` instead of touching your desktop.

This package does **not** import, modify, wrap or simulate F16 / Live Operator. Its production
Gemini adapter imports the repository's existing `ai.gemini_client.GeminiClient`; the bridge does
not call F16 or the separate `WindowsActionExecutor`.

## Honest status

| Area | Status |
|---|---|
| Task manager, queue, lifecycle, cancellation, timeouts, verification, policy hooks | Implemented and tested with mock + real backends (on Linux) |
| Filesystem + process tools (`LocalToolBackend`) | Implemented; tested on Linux. **Not yet run on Windows** |
| Headless browser tools (Playwright) | Implemented in the core; disabled by the production launcher |
| LLM planner (Gemini) | `GeminiPlanner` adapts the existing `ai.gemini_client.GeminiClient`; `DemoPlanner` remains dev/test-only. |
| Production bridge launcher | `python -m background_agent.bridge.production_server`; requires `.env` with `GEMINI_API_KEY` and bridge dependencies. |
| Isolated Windows GUI automation | **NOT implemented.** GUI actions fail closed; needs a `WindowsSandboxBackend` / `VMBackend`. |

## Architecture

```text
Ruby UI (React)  --authenticated localhost bridge-->  BackgroundTaskManager
                                           | queue + scheduler
                                           | per task: supervisor -> worker
                                           v
   GeminiPlanner --> Action --> capability check -> ActionPolicy -> confirmation
                                                   -> ExecutionEnvironment.execute()
                                           |
                                           v
                    Verifier (same environment; never trusts model claim)
                                           |
                                           v
                       COMPLETED / FAILED / CANCELLED / TIMEOUT + outputs
```

## Windows isolation

Real GUI automation that does not hijack the user's desktop needs an environment with its own
input and display. A future Windows Sandbox or VM backend should implement the existing
`ExecutionBackend` / `ExecutionEnvironment` contract. Do **not** use hidden cursors, minimized
windows, a second Python thread, or F16 against the real desktop as a substitute for isolation.

## Safety

Background execution remains bounded and fail-closed. Tasks have runtime/action/turn limits,
repeated-action detection, cancellation and verification. Filesystem operations are confined to
the task workspace and explicitly allowed roots. Child processes do not inherit environment
variables whose names contain KEY/TOKEN/SECRET/PASSWORD/CREDENTIAL.

## Usage

```python
from pathlib import Path
from background_agent import BackgroundTaskManager
from background_agent.backends.local_tools import LocalToolBackend

backend = LocalToolBackend(Path.home() / "RubyBackground", enable_browser=False)
manager = BackgroundTaskManager(backend, planner_factory=lambda task: MyPlanner(task.goal))
manager.start()
task = manager.submit("Organize my notes into report.md")
manager.cancel(task.id)
manager.shutdown()
```

The production Gemini planner can request workspace-confined filesystem actions only. Process,
shell, browser, and GUI actions are disabled. File deletion and overwrites still require the
existing per-action confirmation. Keep background task status separate from Ruby's emotion enum.

## Production bridge

Set `GEMINI_API_KEY` in the repository root `.env`, install `requirements.txt` and
`requirements-bridge.txt`, then run:

```powershell
python -m background_agent.bridge.production_server --bridge-env-file desktop_app/.env.local
```

Start the Electron UI separately from `desktop_app` using `npm run desktop:dev`. The Python
host writes a fresh bearer token to `RUBY_BRIDGE_TOKEN` in the ignored `.env.local`; Electron
reads it in its host process, and the React renderer never receives it. The server binds to
loopback. For demo behavior without Gemini, use `python -m background_agent.bridge.dev_server`.

## Install & test

```powershell
python -m unittest discover -s tests/background_agent -p "test_bg_*.py" -v
python -m unittest discover -s tests -p "test_*.py" -v
# optional:
python -m pytest tests/background_agent
# optional real-browser tests:
python -m pip install playwright
python -m playwright install chromium
```

The task runtime does not provide isolated Windows GUI computer use. That capability comes
only after a real Sandbox/VM execution backend is built and tested on Windows.
