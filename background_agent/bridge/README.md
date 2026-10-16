# Bridge: Python `BackgroundTaskManager` <-> React shell (PR C1)

Local FastAPI + WebSocket server. REST for commands, one WebSocket for live events and confirmation prompts. Python generates the port/token; the React/Vite dev app reads them from env vars. **This PR is Python only; the React client/store/panel/modal is PR C2.**

## Honest status

| Part | Status |
|---|---|
| `BridgeService`, `EventHub`, `ConfirmationBroker`, `BridgeAuth` (stdlib only) | Implemented and tested |
| FastAPI adapter (`app.py`), `BridgeServer`, `dev_server.py` | Implemented; requires FastAPI/uvicorn to execute |
| Windows behaviour | Not tested |
| React client, native-wrapper auth injection, persistence | Not in this PR |

## Security

The bridge binds to loopback only, uses a new bearer token per launch, checks Origin and Host,
rejects wildcard CORS, caps WebSocket connections/frame sizes, and requires authentication before
streaming events. The token is intended for the local development bridge; production packaging
should have the native wrapper inject it rather than exposing it as a bundled public secret.

## REST

- `GET /v1/health`
- `GET /v1/state`
- `POST /v1/tasks` with `{\"goal\":\"...\"}`
- `GET /v1/tasks`
- `GET /v1/tasks/{id}`
- `POST /v1/tasks/{id}/cancel`
- `GET /v1/confirmations`
- `POST /v1/confirmations/{id}` with `{\"approved\":true|false}`
- `POST /v1/backend/reset-quarantine`

Errors use `{\"error\":{\"code\",\"message\"}}`.

## WebSocket `/v1/events`

The client authenticates with a first frame containing the bearer token and optional epoch/last-sequence
information. The server sends a hello/full-state or replay, then streams task, confirmation and activity
frames. Terminal task status events are retained; progress is throttled. Slow clients are closed and
must resync.

## Confirmation flow

A policy CONFIRM decision creates a pending confirmation. The worker waits cooperatively while the bridge
broadcasts the request. The UI explicitly approves or denies exactly one action. Timeout, cancellation,
shutdown, duplicate responses, and broker failure all fail closed. `ConfirmationRequest.details` contains
an unredacted, bounded description for the confirmation UI only; it never appears in progress/snapshots.

## Dev usage

```powershell
pip install -r requirements-bridge.txt
python -m background_agent.bridge.dev_server --env-file desktop_app/.env.local
```

For a real integration, create a `BridgeService` around the existing manager/backend, start it, then start
`BridgeServer`. The React client is deliberately a separate PR so the Python bridge remains UI-independent.
