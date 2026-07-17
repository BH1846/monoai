# MonoAI Gateway 2.0

A sovereignty-grade AI data firewall: an LLM gateway with reversible PII
tokenization, declarative policy governance, per-key auth/budgets/rate
limits, provider fallback chains, streaming, and a tamper-evident audit
chain.

This build is complete through **Phase 4 ("Sovereignty & agentic
governance")** of the planned 4-phase build. See `DECISIONS.md` for every
deviation/simplification made along the way.

## Status — all 4 phases complete

| Phase | Scope | Status |
|---|---|---|
| Phase 1 — Gateway Core | streaming, per-key auth, declarative policy, output scan, provider fallback, multi-turn vault tokens, secrets hygiene | Done |
| Phase 2 — Governance depth & routing intelligence | semantic injection judge, embedding router cascade, OTel observability, evidence-bundle + per-record audit signing, Postgres vault/audit backends | Done |
| Phase 3 — Multi-surface scanning & streaming | `filescan-worker/` (PDF/DOCX/XLSX/CSV scan + redact), output-scan context suppression | Done |
| Phase 4 — Sovereignty & agentic governance | `core/detect/packs/gulf_ar/` (Gulf/Arabic ID pack), `mcp-firewall/` (MCP tool-call firewall), Postgres key store + migration script, `bench/` benchmark harness | Done |

`ner-sidecar/` remains a placeholder (NER still runs in-process via
`core/detect/stages/ner_stage.py`; the HTTP/gRPC sidecar boundary was not
needed). See each subdirectory's own `README.md` for module-level detail,
and `DECISIONS.md` for what was simplified or deferred within each phase.

## Quickstart

```bash
git clone <this-repo> && cd monoai
cp .env.example .env
# Generate real secrets for VALKEY_PASSWORD, SESSION_TOKEN_SECRET, MONOAI_ADMIN_KEY:
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # run 3x, paste into .env

make up          # starts Valkey (docker compose)
uv sync --all-packages
uv run uvicorn app:app --app-dir gateway --port 8000
```

`MONOAI_PROVIDER` defaults to `stub` (no external calls, no API key needed —
good for a first run). Create a virtual key and send a request:

```bash
curl -s -X POST http://127.0.0.1:8000/v1/admin/keys \
  -H "Authorization: Bearer $MONOAI_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"team_id": "demo", "policy_id": "default"}'
# -> {"key": "mk-...", "key_id": "vk_...", ...}

curl -s -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer mk-..." \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Email me at jane@example.com about the invoice"}]}' \
  | python3 -m json.tool
```

The response's `monoai.sanitized_prompt` shows the email replaced with a
`[PII_TOKEN_xxxxxxxxxx]` placeholder before it ever reached the model; the
top-level `choices[0].message.content` has the real email restored. Try
`"stream": true` in the request body for the SSE streaming path.

Run the test suite:

```bash
make test        # == uv run pytest tests/
```

## Architecture

```
request → auth (virtual key, budget, rate limit, model allowlist)
        → policy load (per-key policy_id)
        → sanitize (role-preserving, per message; core/detect + core/policy + core/vault)
        → BLOCK span present? → 422, audited, never reaches the router/LLM
        → route (heuristic difficulty classifier) → provider fallback chain
        → output-scan (catches PII the model leaked, never in the prompt)
        → rehydrate (restore original values for REVERSIBLE tokens)
        → audit (hash-chained record, off the response path)
        → response (or SSE stream)
```

`core/` is a dependency-free-of-service-code shared library (detection,
policy, vault, audit) usable by future surfaces (file scanning, MCP tool
args) without duplicating logic. `gateway/` is the FastAPI service.

## Repo layout

```
core/
  contracts/     pydantic v2 models: spans, policy decisions, scan requests, audit records
  detect/        DetectionPipeline: regex + secrets + NER (ONNX or rule-based fallback) +
                 span repair + locked-span negation handling + span merge
  policy/        YAML policy engine (label -> action), content-hash versioned
  vault/         AES-256-GCM + sealed-box envelope encryption, session-deterministic tokens,
                 pluggable storage (SQLite now, Postgres stub for Phase 2)
  audit/         hash-chained records, JSONL sink, evidence export
gateway/
  api/           chat, health, evidence, admin (key/policy/provider/model CRUD), files (Phase 3 stub)
  auth/          virtual keys, token-bucket rate limiter, budget checks
  providers/     OpenAI-compatible / Ollama / stub adapters, circuit breaker, fallback chain,
                 runtime provider/model registry (registry_store.py) + dynamic per-model router
  router/        request normalizer (4 wire formats) + heuristic difficulty classifier
  pii.py         role-preserving sanitize / output-scan / rehydrate glue
  orchestrator.py the 6-step request spine
  streaming.py   SSE sliding-window rehydrator
policies/        default.yaml, finance_strict.yaml, gulf_sovereign.yaml (Phase 1 stub)
agent/           standalone SENTINEL edge agent (Wazuh-style manager/agent split) — see agent/README.md
tests/           unit/ integration/ adversarial/ e2e/
scripts/         verify_audit_chain.py — standalone verifier to hand to auditors
```

## Manager/agent split (Wazuh-style)

The gateway doubles as the **manager**: enrollment authority, vault, policy
authoring, the hash-chained audit log, and the admin dashboard all stay
central. A lightweight **agent** (`agent/`, its own process, meant for OTHER
hosts) enrolls once, then runs SENTINEL Tier 0/1 detection locally, buffers
events when the manager is unreachable, replays them in order on reconnect,
and pulls policy on an interval — see [`agent/README.md`](agent/README.md).

Manager-side endpoints (in `gateway/api/agents.py`):

```bash
# Admin mints a one-time enrollment token (reuses MONOAI_ADMIN_KEY)
curl -s -X POST http://127.0.0.1:8000/v1/admin/agents/enroll-token \
  -H "Authorization: Bearer $MONOAI_ADMIN_KEY"
# -> {"token": "et-...", "expires_at": ...}

curl -s http://127.0.0.1:8000/v1/admin/agents -H "Authorization: Bearer $MONOAI_ADMIN_KEY"
# -> {"agents": [{"agent_id": "agt_...", "status": "online", "policy_stale": false, ...}]}
```

`POST /v1/agent/enroll` (token + agent pubkey → agent_id + manager pubkey),
`POST /v1/agent/ingest` (PyNaCl-`Box`-sealed events → the **existing**
hash-chained audit log, tagged with `agent_id`), `GET /v1/agent/policy`, and
`POST /v1/agent/heartbeat` are the agent-facing surface. The agent holds only
its own private key + the manager's public key — never any vault/Valkey key
material.

## Provider registry

Beyond the single env-configured `MONOAI_PROVIDER` (stub/ollama/cloud, used
as the difficulty-tier fallback path), an admin can register upstream
provider credentials and models at runtime. Provider API keys are
vault-encrypted at rest (`gateway/providers/registry_store.py`, reusing
`core/vault/crypto.py` — never stored in plaintext). A chat request whose
`model` matches a registered model bypasses the difficulty-tier router
entirely and dispatches straight to that provider/model; `model: "auto"`
(or an unregistered model) falls through to the existing behavior
unchanged.

```bash
# Register a provider (api_key is optional for kind=ollama)
curl -s -X POST http://127.0.0.1:8000/v1/admin/providers \
  -H "Authorization: Bearer $MONOAI_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "groq", "kind": "openai-compatible", "base_url": "https://api.groq.com/openai/v1", "api_key": "gsk_..."}'
# -> {"provider_id": "prov_...", "name": "groq", "kind": "openai-compatible", "base_url": "...", "key_last4": "...", "enabled": true}

curl -s http://127.0.0.1:8000/v1/admin/providers -H "Authorization: Bearer $MONOAI_ADMIN_KEY"
# -> {"providers": [...]}   # key_last4 only, never the full key

# Map a client-facing model name to that provider
curl -s -X POST http://127.0.0.1:8000/v1/admin/models \
  -H "Authorization: Bearer $MONOAI_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model_id": "demo-model", "provider_id": "prov_...", "upstream_model": "llama-3.1-8b-instant"}'

curl -s http://127.0.0.1:8000/v1/admin/models -H "Authorization: Bearer $MONOAI_ADMIN_KEY"
# -> {"models": [{"model_id": "demo-model", "provider_name": "groq", ...}]}

# Mint a virtual key scoped to that model, then chat with it
curl -s -X POST http://127.0.0.1:8000/v1/admin/keys \
  -H "Authorization: Bearer $MONOAI_ADMIN_KEY" -H "Content-Type: application/json" \
  -d '{"model_allowlist": ["demo-model"]}'

curl -s -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer mk-..." -H "Content-Type: application/json" \
  -d '{"model": "demo-model", "messages":[{"role":"user","content":"hi"}]}'
```

## Environment variables

See `.env.example` for the full, documented list. Everything needed to run
locally has a default except the three secrets you must generate
(`VALKEY_PASSWORD`, `SESSION_TOKEN_SECRET`, `MONOAI_ADMIN_KEY`) and, if you
want real model calls, `MONOAI_PROVIDER=cloud` + `CLOUD_API_*`.

## Auditing

Every request writes one hash-chained record to `MONOAI_AUDIT_LOG_PATH`
(`./gateway_audit.jsonl` by default) — labels and counts only, never raw
values. Verify the chain independently:

```bash
uv run python scripts/verify_audit_chain.py gateway_audit.jsonl
```

`GET /v1/evidence/export` returns the same chain as a downloadable bundle
(unsigned in Phase 1 — Ed25519 signing is Phase 2, see `DECISIONS.md`).

## Development

```bash
make lint         # ruff
make typecheck     # mypy --strict on core/ and gateway/
make test          # full pytest suite
```

Porting reference (SENTINEL-2.0 / Lite_Multimodel_switching source this
was built from) lives outside this repo at `../monoai-port-reference/` —
see `DECISIONS.md` for why.

