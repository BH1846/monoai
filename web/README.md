# MonoAI Gateway Console

A React/Express console for the MonoAI gateway (`../gateway`). The browser never
calls the gateway directly — every gateway call goes through this app's own
Express server (`server.ts`), which injects credentials server-side from
request headers (or `.env` fallbacks) so no CORS is ever needed and no key is
ever bundled into client JS or written to localStorage.

## Run Locally

**Prerequisites:** Node.js, and the MonoAI gateway running (see repo root README).

1. Start the gateway (from the repo root):
   ```bash
   make up          # starts Valkey (docker compose)
   uv sync --all-packages
   uv run uvicorn app:app --app-dir gateway --port 8000
   ```

2. Install and run this console:
   ```bash
   cd web
   npm install
   npm run dev
   ```
   Open http://localhost:3000.

3. Copy `.env.example` to `.env` if you want fallback credentials baked in for
   local dev (optional — you can also just paste them into the UI each
   session):
   ```bash
   cp .env.example .env
   ```

4. In the console:
   - Sign in, then open **Admin > Settings**.
   - Paste the gateway's admin key (`MONOAI_ADMIN_KEY` on the gateway) into
     **Admin API Key**, confirm the **Gateway Base URL** (defaults to
     `http://localhost:8000`), then click **Test Connection** — it should
     report the gateway's `/health/ready` checks.
   - Click **Save Connection**. The admin key and gateway URL are kept in
     `sessionStorage` only (cleared when you close the tab), never
     localStorage, never the client bundle.
   - Go to **Admin > Providers**: register a provider (name, kind, base URL,
     API key) and a model against it. These persist in the gateway's own
     SQLite store, so they survive a page reload.
   - Go to **Admin > Users**: create a virtual key, optionally scoped to a
     model allowlist, with a monthly budget and rate limit. The raw key is
     shown once — copy it.
   - Paste that virtual key into **Admin > Settings > Chat Virtual Key** (or
     leave blank to rely on the `MONOAI_VIRTUAL_KEY` env fallback).
   - Return to the chat workspace, pick the registered model from the model
     picker, and send a message. Try a prompt containing PII (redacted card),
     a policy-blocked prompt (blocked card), and a model outside your key's
     allowlist (blocked card, HTTP 403).

## Env vars

See `.env.example`:

- `MONOAI_GATEWAY_URL` — default gateway base URL (overridable per-session
  from the Settings panel).
- `MONOAI_ADMIN_KEY` — fallback admin bearer if no `x-monoai-admin-key` header
  is sent (i.e. if you don't paste one into Settings).
- `MONOAI_VIRTUAL_KEY` — fallback chat virtual key if no
  `x-monoai-virtual-key` header is sent.
