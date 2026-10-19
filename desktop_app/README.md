# Ruby Agent Desktop

Ruby Agent is a Windows desktop preview built from the React shell and an Electron host.

## Run locally

```powershell
cd desktop_app
npm install
npm run desktop:dev
```

The app opens as a compact Ruby orb. Click it to expand the control center. The frameless
window has native minimize, maximize, close, and drag controls. `npm run dev` still starts
the browser preview without Electron.

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

## Current scope

The screens still use mock data and placeholder views. The desktop host does **not** yet
connect to a real planner or background task bridge, and it does not provide isolated
Windows GUI automation. Those capabilities need their own UI integration and a real
Windows Sandbox or VM backend.

The Electron renderer uses context isolation, sandboxing, and a narrow preload API for
window controls. It does not receive Node.js access.
