# Ruby Agent Desktop

Ruby Agent is a Windows desktop preview built from the React shell and an Electron host.

## Run locally

Configure `GEMINI_API_KEY` in the repository root `.env` (copy `.env.example` first),
then install Python and bridge dependencies:

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-bridge.txt
python -m background_agent.bridge.production_server --bridge-env-file desktop_app/.env.local
```

In a second terminal, start Electron and Vite:

```powershell
cd desktop_app
npm install
npm run desktop:dev
```

The production launcher validates the Gemini key, starts `GeminiPlanner` with the existing
`ai.gemini_client.GeminiClient`, and runs the current bridge. It generates a fresh bearer
token and writes `RUBY_BRIDGE_URL` / `RUBY_BRIDGE_TOKEN` to `.env.local`. Those names do not
use Vite's `VITE_` prefix. Electron reads them in the host process; the renderer receives
only task methods through preload. The bridge binds to loopback and requires the token for
task/state HTTP operations. The UI polls task progress, results, errors, and pending
confirmations.

The app opens as a compact Ruby orb. Click it to expand the control center. `npm run dev`
starts a browser preview without Electron; the browser preview cannot authenticate to the bridge.

Build a Windows installer:

```powershell
npm run desktop:dist
```

The NSIS installer and unpacked app are written to `release/`. To build an unpacked app
for the current platform, use:

```powershell
npm run desktop:pack
```

For a browser-only production build:

```powershell
npm run build
```

Node.js 22.12 or newer is required. Package versions are pinned in `package.json` and
`package-lock.json` so the preview and installer builds use the same dependencies.

## Runtime boundary

The development command still starts `DemoPlanner`; it never calls Gemini. Production uses
`GeminiPlanner` and supports workspace-confined filesystem tasks. Destructive file actions
and overwrites require per-action approval. Process/shell, browser, and GUI actions are
disabled in the production bridge. The existing background package has no isolated Windows
GUI backend, so opening Notepad and controlling the active desktop are not supported by
this task interface. The separate F16 path is unchanged and is not called by the bridge.

Run the deterministic tests without a Gemini API call:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python -m unittest discover -s tests/background_agent -p "test_bg_*.py" -v
```

The Electron renderer uses context isolation, sandboxing, and a narrow preload API for
window controls and bridge operations. It does not receive Node.js access or the bridge token.
