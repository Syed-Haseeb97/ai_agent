# Ruby Background Agent (core package)

Lets Ruby work on a long task **in a separate execution environment** while you keep using
your computer. UI-independent: the React shell will consume it through a bridge in a later PR.

> **The guarantee this package is built around:** selecting *Background Task* must never mean
> Ruby moves your mouse, types on your keyboard, or takes focus on your real desktop.
> The only backend shipped here (`LocalToolBackend`) has **no mouse/keyboard/screen-control
> capability at all**. GUI work returns `GUI_ISOLATION_REQUIRED` instead of touching your desktop.

This package does **not** import, modify, wrap or simulate F16 / Live Operator, and it does not
import anything from the rest of the repo. It is additive.

## Honest status

| Area | Status |
|---|---|
| Task manager, queue, lifecycle, cancellation, timeouts, verification, policy hooks | Implemented and tested with mock + real backends (on Linux) |
| Filesystem + process tools (`LocalToolBackend`) | Implemented; tested on Linux. **Not yet run on Windows** |
| Headless browser tools (Playwright) | Implemented; real Chromium integration test passes on **Linux**; not run on Windows |
| **Isolated Windows GUI automation** | **NOT implemented.** Needs a `WindowsSandboxBackend` / `VMBackend` |
| LLM planner (Gemini) | **Not implemented.** Only the `Planner` interface + `ScriptedPlanner`. |
| UI mode switch, task panel, notification, Ruby-state bridge | **Not in this PR** |

## Architecture

```text
Ruby UI (React)  --bridge (later PR)-->  BackgroundTaskManager
                                           | queue + scheduler
                                           | per task: supervisor -> worker
                                           v
   Planner --> Action --> capability check -> ActionPolicy -> confirmation
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

The React bridge will later expose submit/cancel/list operations and stream task events. Keep
background activity separate from Ruby's emotion enum.

## Install & test

```powershell
python -m unittest discover -s tests/background_agent -p "test_bg_*.py" -v
# optional:
python -m pytest tests/background_agent
# optional real-browser tests:
python -m pip install playwright
python -m playwright install chromium
```

The current implementation is a **foundation**, not a claim of true isolated Windows GUI
computer use. That capability comes only after a real Sandbox/VM execution backend is built
and tested on Windows.