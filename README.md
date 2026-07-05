# monoai-gateway

A simplified LLM-governance gateway built by wiring together two existing
libraries as-is:

- **PII layer**: [SENTINEL-2.0](./SENTINEL-2.0) (`pii_pipeline`) — detects,
  classifies, and reversibly tokenizes PII; owns the vault.
- **Model-selection layer**: [Lite_Multimodel_switching](./Lite_Multimodel_switching)
  (`monoai_router`) — normalizes the request, classifies difficulty, and
  routes to exactly one model per difficulty tier.

`monoai_gateway/` implements a **reduced, 6-step version** of the full
9-step MonoAI request flow:

```
request → scan/redact PII (SENTINEL) → select model (router) → call LLM
        → rehydrate PII into response → audit log → return
```

## Why this exists / ground-truth notes

Both source repos were consumed **as libraries, unmodified internally**.
Two files were added purely for packaging/config, not logic:

- `SENTINEL-2.0/pyproject.toml` — the repo had no packaging metadata at all
  (no `setup.py`/`pyproject.toml`), so `pip install -e` wasn't possible
  until this was added.
- `SENTINEL-2.0/.env` — pre-existing in the repo; only `VALKEY_PORT` was
  changed (6379 → 6380) to point at this project's own dedicated Valkey
  container instead of an unrelated Redis already running on the host's
  6379.

`Lite_Multimodel_switching/SENTINEL_INTEGRATION_SPEC.md` describes a
fictional integration (`async SENTINEL.scan()`, `[[EMAIL_001]]` tokens, a
hand-built `VaultManager`) that **does not exist in the code**. This
gateway is built against the real `pii_pipeline.Pipeline` API instead —
see `monoai_gateway/pii.py`.

## Setup

```bash
# 1. Start Valkey (SENTINEL's vault master-key store — hard dependency,
#    no on-disk fallback). Runs on 6380 to avoid clashing with any
#    pre-existing Redis/Valkey on the default 6379.
VALKEY_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))") docker compose up -d

# 2. Create a venv and install both source repos editable + the gateway's deps
python3 -m venv .venv && source .venv/bin/activate
pip install -e ./SENTINEL-2.0 -e ./Lite_Multimodel_switching -r requirements.txt

# 3. Run the server (StubProvider by default — no external calls, no API key)
uvicorn monoai_gateway.app:app --port 8000

# ...or route to a real cloud model: paste your key into .env (see below),
# set CLOUD_API_BASE_URL/CLOUD_MODEL_* to whatever vendor+models you want,
# then:
MONOAI_PROVIDER=cloud uvicorn monoai_gateway.app:app --port 8000

# 4. Try it
curl -s -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Email me at jane@example.com, say hi."}]}' | python3 -m json.tool
```

Run the tests (needs Valkey up, same as above):

```bash
pytest tests/ -v
```

## Environment variables

| Variable | Owner | Default | Purpose |
|---|---|---|---|
| `VALKEY_HOST` / `VALKEY_PORT` / `VALKEY_PASSWORD` / `VALKEY_KEY_NAME` | `pii_pipeline.vault` | from `SENTINEL-2.0/.env` | Vault master-key storage. Hard requirement — `Pipeline()` will not construct without a reachable Valkey. |
| `PII_VAULT_STORAGE_PATH` | gateway | `./pii_vault.sqlite` | Where the (encrypted) vault entries are persisted on disk. |
| `PII_USE_ONNX_NER` | gateway | `true` | Use the real ONNX NER model (needs `onnxruntime`+`tokenizers`, in `requirements.txt`) instead of SENTINEL's rule-based fallback. Matters a lot for recall — the fallback's PERSON detector only fires after a capitalized name (misses "my name is deepak", catches "my name is Deepak"). Auto-falls back to rule-based if the model/runtime aren't available. |
| `MONOAI_PROVIDER` | gateway | `stub` | `stub` (no external calls, for demos/tests), `ollama` (local inference — needs `ollama serve` + pulled models), or `cloud` (any OpenAI-compatible API — see below). |
| `OLLAMA_BASE_URL` | gateway | `http://localhost:11434` | Only used when `MONOAI_PROVIDER=ollama`. |
| `CLOUD_API_BASE_URL` / `CLOUD_API_KEY` / `CLOUD_PROVIDER_NAME` | gateway | from `.env` | Only used when `MONOAI_PROVIDER=cloud`. Any vendor speaking the OpenAI chat-completions wire format (Groq, OpenAI, OpenRouter, Together, Fireworks, ...) — see `monoai_gateway/providers.py`. |
| `CLOUD_MODEL_SIMPLE` / `CLOUD_MODEL_MODERATE` / `CLOUD_MODEL_COMPLEX` | gateway | from `.env` | Which real model each router difficulty tier dispatches to when `MONOAI_PROVIDER=cloud`. |
| `MONOAI_ROUTER_LOG_PATH` | gateway | `./lite_router_log.jsonl` | `LiteRouter`'s own per-request JSONL log (request_id, difficulty, model_id, latency — no content). |
| `MONOAI_AUDIT_LOG_PATH` | gateway | `./gateway_audit.jsonl` | This gateway's audit trail (see below). |
| `MONOAI_BEARER_TOKEN` | gateway | unset (auth disabled) | If set, `POST /v1/chat/completions` requires `Authorization: Bearer <value>`. |

### Using a cloud model (`.env`)

A `.env` file at the repo root (auto-loaded by `monoai_gateway/config.py`;
real environment variables still take precedence) is where you paste your
API key and pick which model each difficulty tier routes to:

```bash
MONOAI_PROVIDER=cloud
CLOUD_API_BASE_URL=https://api.groq.com/openai/v1   # or OpenAI/OpenRouter/Together/Fireworks/...
CLOUD_API_KEY=your-key-here
CLOUD_PROVIDER_NAME=groq
CLOUD_MODEL_SIMPLE=llama-3.1-8b-instant
CLOUD_MODEL_MODERATE=llama-3.3-70b-versatile
CLOUD_MODEL_COMPLEX=qwen/qwen3-32b
```

`monoai_router`'s dispatcher (`MODEL_BY_DIFFICULTY`, internal to that repo)
hardcodes Ollama-style tags per tier — `monoai_gateway/providers.py`'s
`OpenAICompatibleProvider` remaps those tags to whichever real model you
configured per tier at the provider boundary, so the router itself is
untouched. Swapping `CLOUD_API_BASE_URL` to any other OpenAI-compatible
vendor's endpoint (and `CLOUD_MODEL_*` to that vendor's model names) is all
that's needed to switch providers — no new adapter code.

## The reduced flow, step by step (`monoai_gateway/orchestrator.py`)

1. **Normalize** — the raw payload (OpenAI/Anthropic/Gemini/native) is
   normalized via `monoai_router`'s `RequestNormalizer`; all message text is
   collected into one string.
2. **Scan/redact** — `PiiGuard.sanitize(text)` runs SENTINEL's real
   `Pipeline.sanitize()` in a worker thread (`asyncio.to_thread`, since
   it's synchronous). Any `BLOCK`-classified span (credit card, gov ID,
   secret) rejects the request with HTTP 422 **before** the router or any
   model ever sees the prompt — BLOCK spans are tokenized into the
   sanitized prompt but SENTINEL deliberately never vaults them, so they
   could never be rehydrated back out anyway.
3. **Select model + call LLM** — the *sanitized* text is routed through
   `LiteRouter.route()`, which classifies difficulty (simple/moderate/complex,
   heuristic/regex-based) and dispatches to exactly one model per tier. The
   provider only ever sees `[PII_TOKEN_xxxx]` placeholders.
4. **Rehydrate** — `PiiGuard.complete()` restores original values from
   SENTINEL's vault. If the model dropped or duplicated a placeholder,
   `Pipeline.complete()` raises `RehydrationReviewRequired`; the gateway
   catches this and returns best-effort content with
   `monoai.review_required: true` and `monoai.unresolved_tokens` populated,
   rather than failing the request.
5. **Audit** — one JSONL line per request, written via a FastAPI
   `BackgroundTask` (after the HTTP response is sent) to
   `MONOAI_AUDIT_LOG_PATH`: `request_id`, `session_id`, `difficulty`,
   `model_id`, `provider`, `span_counts_by_label`, `redacted_count`,
   `unresolved_tokens`, `review_required`, and per-stage latencies.
6. **Return** — an OpenAI-compatible `chat.completion` response, plus a
   `monoai` extension object with `session_id`/`provider`/`difficulty`/
   `review_required`/`unresolved_tokens`.

## A known, deliberate simplification

Step 1 collects **all** message text into a single string and sanitizes it
in **one** `Pipeline.sanitize()` call, then routes it as a single
synthetic user message. This is because SENTINEL's token IDs
(`PII_TOKEN_0001`, `0002`, ...) are a **per-call counter** — calling
`sanitize()` once per message would produce colliding token IDs across
messages. Multi-turn conversational structure is therefore collapsed for
the router/LLM call. A production version would need either a
cross-message token counter inside SENTINEL, or per-message sanitize calls
sharing one `session_id` with a counter offset passed in.

## What's real vs. stubbed (honest accounting against the 9-step MonoAI flow)

| # | Full MonoAI step | Status here |
|---|---|---|
| 1 | Auth / RBAC | **Stubbed** — single optional bearer token (`MONOAI_BEARER_TOKEN`), no RBAC, no per-key identity. |
| 2 | Policy engine | **Omitted** — no policy evaluation beyond SENTINEL's fixed BLOCK/REVERSIBLE/PRESERVE label policy. |
| 3 | Semantic / exact cache | **Omitted.** |
| 4 | Budget enforcement | **Omitted** — usage is returned in the response but nothing is metered or capped. |
| 5 | **PII scan/redact** | **Real** — SENTINEL-2.0's actual `Pipeline.sanitize()`/`complete()`, real vault, real Valkey-backed master key, real ONNX NER model (`PII_USE_ONNX_NER=true`, the default — see below). |
| 6 | **Model selection/routing** | **Real** — `monoai_router`'s actual `LiteRouter` (normalizer → heuristic difficulty classifier → dispatcher → provider). |
| 7 | LLM call | **Real for the provider it calls** — `StubProvider` (default, no external calls), `OllamaProvider` (local inference, via `MONOAI_PROVIDER=ollama`), or any OpenAI-compatible cloud API (Groq/OpenAI/OpenRouter/Together/Fireworks/...) via `MONOAI_PROVIDER=cloud` + `.env` (gateway-side `OpenAICompatibleProvider`, `monoai_gateway/providers.py`). |
| 8 | Streaming | **Omitted** — `stream` is accepted in normalized payloads but ignored; responses are always whole. |
| 9 | Response-side re-scan / prompt-injection defenses | **Omitted** beyond what SENTINEL's redaction already does on the way in; no scan of the model's raw output before rehydration. |
| — | Postgres / vector store | **Omitted** — audit trail is an append-only JSONL file, not a queryable store. |
| — | **Rehydration + audit** | **Real** — see steps 4–5 above. |

## Repo layout

```
monoai_gateway/
  config.py         # env-driven settings (loads repo-root .env)
  pii.py             # async wrapper over pii_pipeline.Pipeline
  orchestrator.py    # the reduced flow
  audit.py           # append-only JSONL audit log
  providers.py        # OpenAICompatibleProvider (any cloud vendor via .env)
  app.py             # FastAPI: POST /v1/chat/completions, GET /health
tests/
  test_orchestrator.py   # end-to-end: real Pipeline + StubProvider
.env                       # API keys / cloud model choices (paste yours here)
docker-compose.yml        # dedicated Valkey for local dev
requirements.txt
```
