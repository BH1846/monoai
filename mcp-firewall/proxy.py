"""MCP tool firewall proxy (Phase 4, G-agentic-governance): sits
between an agentic LLM host (an MCP client) and a real downstream MCP
tool-execution node, intercepting `tools/call` JSON-RPC requests to
scan+police their string arguments (scanner.py, rules.py) before
forwarding -- or refusing -- the call.

Client-facing side: a spec-correct MCP SSE transport handshake --
  1. Client GETs /sse. Server opens a text/event-stream and immediately
     sends `event: endpoint` / `data: /messages?session_id=<uuid>`.
  2. Client POSTs each JSON-RPC message to that URL; server ACKs with
     202 and processes it asynchronously.
  3. The eventual JSON-RPC response is pushed back on the ORIGINAL SSE
     stream as `event: message` / `data: <json-rpc response>`.
This matches the MCP spec's SSE transport (see
modelcontextprotocol.io/specification/.../basic/transports) and the
reference Python SDK's SseServerTransport shape.

Upstream-facing side (this proxy -> the real tool node) is
SIMPLIFIED: a single synchronous `POST {MCP_UPSTREAM_URL}/messages`
expecting the JSON-RPC response directly in the HTTP response body,
not a second SSE stream. Real MCP servers that themselves only speak
SSE (not a synchronous request/response HTTP endpoint) are NOT
supported by this proxy as shipped -- documented honestly in
DECISIONS.md rather than left as a silent gap. The client-facing SSE
handshake above is independently exercised in this environment; the
upstream leg is exercised against a companion HTTP-POST mock, not a
live third-party MCP server.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import redis
from detect.pipeline import DetectionPipeline
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from vault.crypto import VaultCrypto
from vault.storage.base import VaultStore
from vault.storage.postgres_store import PostgresVaultStore
from vault.storage.sqlite_store import SqliteVaultStore

from config import Settings, load_settings
from rules import ToolFirewallConfig
from scanner import ToolCallBlockedError, ToolFirewall

_DEFAULT_TOOL_RULES_PATH = Path(__file__).resolve().parent / "tool_rules.yaml"

_KEEPALIVE_S = 15.0


def _build_vault_store(settings: Settings, vault_crypto: VaultCrypto) -> VaultStore:
    if settings.vault_backend == "postgres":
        if not settings.vault_postgres_dsn:
            raise ValueError("VAULT_BACKEND=postgres requires VAULT_POSTGRES_DSN")
        return PostgresVaultStore(vault_crypto, settings.vault_postgres_dsn)
    return SqliteVaultStore(vault_crypto, storage_path=settings.vault_storage_path)


def build_firewall(settings: Settings) -> ToolFirewall:
    valkey_client = redis.Redis(host=settings.valkey_host, port=settings.valkey_port, password=settings.valkey_password)
    vault_crypto = VaultCrypto(valkey_client, key_name=settings.valkey_key_name)
    vault_store = _build_vault_store(settings, vault_crypto)
    pipeline = DetectionPipeline(use_onnx_ner=False)

    rules_path = settings.tool_rules_path or str(_DEFAULT_TOOL_RULES_PATH)
    config = ToolFirewallConfig.load(rules_path) if Path(rules_path).is_file() else ToolFirewallConfig.empty()

    return ToolFirewall(pipeline, vault_store, config, settings.session_token_secret)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Deferred to app startup (not module import time) so a live
    # Valkey connection is only required once the service actually
    # starts serving -- matches gateway/app.py's lifespan pattern, and
    # lets tests construct the app with a stand-in firewall via
    # app.state instead of a real Redis connection.
    settings = load_settings()
    app.state.settings = settings
    app.state.firewall = build_firewall(settings)
    app.state.sessions = {}
    yield


app = FastAPI(title="monoai-mcp-firewall", lifespan=lifespan)


@app.get("/sse")
async def sse_endpoint(request: Request) -> StreamingResponse:
    session_id = uuid.uuid4().hex
    queue: asyncio.Queue = asyncio.Queue()
    request.app.state.sessions[session_id] = queue

    async def event_stream():
        yield f"event: endpoint\ndata: /messages?session_id={session_id}\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=_KEEPALIVE_S)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"event: message\ndata: {json.dumps(message)}\n\n"
        finally:
            request.app.state.sessions.pop(session_id, None)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/messages")
async def messages_endpoint(request: Request, session_id: str) -> JSONResponse:
    queue = request.app.state.sessions.get(session_id)
    if queue is None:
        return JSONResponse(status_code=404, content={"error": "unknown session_id"})

    message = await request.json()
    asyncio.create_task(
        _handle_message(request.app.state.firewall, request.app.state.settings.mcp_upstream_url, session_id, queue, message)
    )
    return JSONResponse(status_code=202, content=None)


async def _handle_message(
    firewall: ToolFirewall, upstream_url: str, session_id: str, queue: asyncio.Queue, message: dict[str, Any]
) -> None:
    if message.get("method") == "tools/call":
        params = message.get("params") or {}
        tool_name = params.get("name", "")
        arguments = dict(params.get("arguments") or {})

        try:
            results = firewall.scan_call(session_id, tool_name, arguments)
        except ToolCallBlockedError as err:
            await queue.put({
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "error": {
                    "code": -32001,
                    "message": str(err),
                    "data": {"tool": err.tool_name, "arg": err.arg_name, "labels": err.span_labels},
                },
            })
            return

        for arg_name, result in results.items():
            arguments[arg_name] = result.value
        message = {**message, "params": {**params, "arguments": arguments}}

    response = await _forward_upstream(upstream_url, message)
    if response is not None:
        await queue.put(response)


async def _forward_upstream(upstream_url: str, message: dict[str, Any]) -> dict[str, Any] | None:
    """Best-effort forward to the real downstream MCP tool node (see
    module docstring for the synchronous-POST simplification). Any
    connection failure or non-2xx response is swallowed -- the calling
    agent simply sees the request time out, same as any other
    transport failure, rather than crashing the firewall process."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{upstream_url.rstrip('/')}/messages", json=message)
            resp.raise_for_status()
            return resp.json() if resp.content else None
    except (httpx.HTTPError, ValueError):
        return None


@app.get("/health/live")
async def health_live() -> dict:
    return {"status": "ok"}
