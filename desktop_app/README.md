# Ruby Agent Desktop

PR A is the UI-only scaffold for Ruby's agent-native Windows command center.

## Run locally

```bash
cd desktop_app
npm install
npm run dev
```

For a production build:

```bash
npm run build
```

## Scope

This scaffold intentionally contains mock data and placeholder views. It does **not** implement F16 execution, background execution, Windows isolation, real task persistence, or real API/settings wiring.

The shell is designed around an agent-control-center model: Home, Chat, Agents / Sessions, Tasks, Projects, History, and Settings. The Ruby orb is represented as a UI placeholder and should be replaced/wired to the existing Liquid Blob component through the future desktop bridge.

## Planned follow-up

PR B will add the background execution architecture and isolated computer-use backend without allowing background tasks to take over the user's active desktop.
