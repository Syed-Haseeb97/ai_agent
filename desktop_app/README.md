# Ruby Agent Desktop

Ruby Agent is a Windows desktop preview built from the React shell and an Electron host.

## Run locally

Start the Python bridge in a separate terminal first:

```powershell
python -m background_agent.bridge.dev_server --env-file desktop_app/.env.local --token-file desktop_app/.ruby-bridge-token
```

Then start Electron and Vite:

```powershell
cd desktop_app
npm install
npm run desktop:dev
```

Electron reads the bridge URL and bearer token from `.env.local` in the host process. The
renderer receives only task methods through preload; the token is not included in the Vite
bundle. The app polls bridge state and displays task progress, results, errors, and pending
action confirmations. Submission, cancellation, and approve/deny responses use the same
authenticated localhost API.

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

The checked-in `background_agent.bridge.dev_server` intentionally uses a demo planner to
exercise the bridge and confirmation flow. It is not the Gemini assistant. The Python
background package still has no production planner or packaged runtime launcher, and it
does not provide isolated Windows GUI automation. A production app needs the Python host to
start the bridge with the real assistant service and a supported execution backend.

The Electron renderer uses context isolation, sandboxing, and a narrow preload API for
window controls and bridge operations. It does not receive Node.js access or the bridge token.
