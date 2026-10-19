# Ruby localhost bridge

FastAPI REST and WebSocket transport for the existing `BackgroundTaskManager`. The Electron host polls REST and keeps the bearer token private from React.

## Runtime modes

| Mode | Command | Planner |
|---|---|---|
| Development/demo | `python -m background_agent.bridge.dev_server --env-file desktop_app/.env.local` | `DemoPlanner`; deterministic demo behavior, no Gemini request |
| Production | `python -m background_agent.bridge.production_server --bridge-env-file desktop_app/.env.local` | `GeminiPlanner` using `ai.gemini_client.GeminiClient` |

Production requires `GEMINI_API_KEY` in root `.env` or the process environment. Install `requirements.txt` and `requirements-bridge.txt` first. Start Electron separately with `cd desktop_app; npm run desktop:dev`.

## Security

The server binds only to loopback, authenticates protected endpoints with a random bearer token, checks Host and allowed Origin headers, rejects wildcard CORS, and limits WebSocket connections/frame sizes. The launcher writes `RUBY_BRIDGE_URL` and `RUBY_BRIDGE_TOKEN` to ignored `desktop_app/.env.local`; it never prints the token and these names do not use Vite's `VITE_` prefix. Electron reads the values inside the host process and React gets only narrow preload methods.

The Electron HTTP client omits Origin, as it is a native host request; it still sends the bearer token and uses the loopback Host. Browser-origin requests must match the explicit origin allowlist.

## REST

- `GET /v1/health`
- `GET /v1/state`
- `POST /v1/tasks` with `{"goal":"..."}`
- `GET /v1/tasks`
- `GET /v1/tasks/{id}`
- `POST /v1/tasks/{id}/cancel`
- `GET /v1/confirmations`
- `POST /v1/confirmations/{id}` with `{"approved":true|false}`
- `POST /v1/backend/reset-quarantine`

Errors use `{"error":{"code","message"}}`.

## WebSocket `/v1/events`

The client authenticates with a first frame containing the bearer token and optional epoch/last-sequence information. The server sends a hello/full-state or replay, then streams task, confirmation, and activity frames. Slow clients must reconnect and resync. The current Electron UI polls the REST state API instead.

## Production action boundary

`GeminiPlanner` returns strict JSON decisions as `Action` or `Finish`. It cannot execute anything. Production advertises only workspace-confined filesystem actions to the planner; the worker still checks capabilities and `DefaultActionPolicy` before execution. Deletes and overwrites require one-time approval through the existing broker. Process/shell, browser, and GUI actions are disabled. GUI remains unsupported until an isolated Windows Sandbox/VM backend exists; F16 and the separate `WindowsActionExecutor` are not invoked by the bridge.

## Tests

```powershell
python -m unittest discover -s tests/background_agent -p "test_bg_*.py" -v
python -m unittest discover -s tests -p "test_*.py" -v
```
