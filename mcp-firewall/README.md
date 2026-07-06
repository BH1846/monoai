Phase 4: MCP tool-call firewall proxy — intercepts `tools/call` JSON-RPC
requests between an agentic LLM host (MCP client) and a real downstream MCP
tool-execution node, scanning string arguments via `core/detect` and
applying a per-(tool, arg) action (`BLOCK`/`REVERSIBLE`/`PRESERVE`) from
`tool_rules.yaml`.

Run standalone: `uv run uvicorn proxy:app --app-dir mcp-firewall --port 8002`

- `proxy.py` — FastAPI app implementing the MCP SSE transport (`GET /sse` +
  `POST /messages?session_id=...`) on the client-facing side; a simplified
  synchronous HTTP POST on the upstream-facing side (see its module
  docstring for the exact scope boundary — this has NOT been exercised
  against a live third-party MCP server, only a mock).
- `rules.py` — `ToolFirewallConfig`, the `tools.<name>.args.<arg>: ACTION`
  YAML schema.
- `scanner.py` — `ToolFirewall`: runs `core/detect`'s `DetectionPipeline`
  over each string argument, applies BLOCK/REVERSIBLE/PRESERVE.
- `config.py` — reuses the SAME `VALKEY_*`/`VAULT_BACKEND`/
  `PII_VAULT_STORAGE_PATH`/`SESSION_TOKEN_SECRET` env vars as
  `gateway/config.py`, so REVERSIBLE-tokenized tool arguments land in the
  same vault namespace a co-deployed gateway's chat sessions already use.
- `tool_rules.yaml` — example rule file matching the spec's `bash.command:
  BLOCK` shape.

See DECISIONS.md for the full list of scope boundaries (SSE-vs-HTTP on the
upstream leg, session store, etc).
