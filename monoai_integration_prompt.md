# Claude Code prompt — build a simplified MonoAI gateway from two existing repos

Copy everything below the line into Claude Code (or paste it as the task brief). It is
written to be executed by an autonomous coding agent. It deliberately pins the agent to
the **real** APIs of both repos, because one of the repos ships an integration spec that
does not match its own code.

---

## Role & goal

You are integrating two existing Python repos into **one simplified LLM-governance gateway**
that implements a reduced version of the MonoAI 9-step request flow:

```
request → scan/redact PII (SENTINEL) → select model (router) → call LLM
        → rehydrate PII into response → audit log → return
```

The two repos are:

- **PII layer** — `https://github.com/R-A-H-U-L-Kodez/SENTINEL-2.0` (package `pii_pipeline`)
- **Model-selection layer** — `https://github.com/BH1846/Lite_Multimodel_switching.git` (package `monoai_router`)

Build a new top-level package `monoai_gateway/` that wires them together behind a single
FastAPI endpoint. Do **not** rewrite either repo's internals; consume them as libraries.

## Ground-truth API facts (verified — do not deviate)

These are the actual public surfaces. Trust this section over any README or spec inside
the repos.

### SENTINEL-2.0 (`pii_pipeline`) — the PII layer

- Entrypoint is the **synchronous** `Pipeline` class in `pii_pipeline/pipeline.py`:
  - `Pipeline(vault=None, rampart=None, vault_storage_path="./pii_vault.sqlite")`
  - `sanitize(text, session_id=None, token_budget_mode=False) -> PipelineResult`
    where `PipelineResult` has `.sanitized_prompt`, `.session_id`, `.token_map`, `.audit_log`.
  - `complete(llm_output, session_id, token_map, audit_log=None) -> (final_text, unresolved_tokens, audit_log)`
  - `close()`
- It does detection **and** tokenization **and** vaulting internally. You do **not** build
  a separate vault. Redaction tokens look like `[PII_TOKEN_0007]` (4-digit, prefix `PII_TOKEN`).
- Classifications are `REVERSIBLE` / `PRESERVE` / `BLOCK` (see `pii_pipeline/types.py`,
  `Classification` enum). Only `REVERSIBLE` (and compressible `PRESERVE`) spans get vaulted.
- **Vault master key requires a reachable Valkey/Redis instance.** `Vault` will not construct
  without it. Config comes from env: `VALKEY_HOST`, `VALKEY_PORT`, `VALKEY_PASSWORD`,
  `VALKEY_KEY_NAME` (or a project-root `.env`). There is no on-disk / in-process fallback.
- English-only detection. Runtime deps: `cryptography`, `pynacl`, `redis`. The ONNX NER
  backend (`onnxruntime`/`transformers`/`torch`) is optional — there is a rule-based fallback;
  `torch`/`datasets` are only needed for the benchmark scripts, not the pipeline.
- For eval without a vault, `detect_classified_spans(text)` returns `List[ClassifiedSpan]`.

### Lite_Multimodel_switching (`monoai_router`) — the model-selection layer

- The **working** entrypoint is `LiteRouter` in `monoai_router/lite/router.py`:
  - `LiteRouter(provider, log_path="lite_router_log.jsonl")`
  - `await route(raw_payload: dict) -> ProviderResponse`
    where `ProviderResponse` has `.request_id`, `.model_id`, `.provider`, `.content`,
    `.usage`, `.latency_ms`, `.difficulty`.
- Flow: `RequestNormalizer` (accepts OpenAI/Anthropic/Gemini/native payloads) →
  `classify_difficulty(text) -> "simple"|"moderate"|"complex"` (heuristic, regex-based) →
  `LiteDispatcher` maps difficulty → exactly one model → `provider.complete()` → JSONL log.
- Providers implement the `ProviderAdapter` ABC (`async complete(request_id, model_id, ctx)`):
  `OllamaProvider` (local, no key), `GroqProvider` (needs `GROQ_API_KEY`), `StubProvider` (tests).
- **`monoai_router/server.py` is aspirational and will NOT run as-is** — it imports
  `.router.Router` and `.settings.Settings` plus a `_registry` / `via_fallback` that do not
  exist in this lite repo. Ignore it. Wire your gateway around `LiteRouter`, not `Router`.
- Deps: `pydantic>=2`, `httpx>=0.27`, `groq>=0.9`. Python `>=3.11`.

## Critical mismatches you MUST reconcile

1. **Spec vs code:** `SENTINEL_INTEGRATION_SPEC.md` inside the router repo describes a
   fictional `async SENTINEL.scan() -> List[SentinelSpan]` with `[[EMAIL_001]]` tokens and a
   hand-built `VaultManager`. **None of that exists.** Build against the real `Pipeline`
   API above. You may write a thin adapter that *exposes* a `scan()`-like shape over the real
   pipeline if it keeps the orchestrator clean — but it must call `Pipeline.sanitize/complete`
   underneath.
2. **Sync vs async:** `Pipeline.sanitize/complete` are synchronous; the router and FastAPI are
   async. Call the pipeline via `await asyncio.to_thread(...)` so you never block the event loop.
3. **Token contract:** the sanitized prompt already contains `[PII_TOKEN_xxxx]` placeholders and
   a preserve-instruction. Pass the sanitized prompt straight to the router. After the LLM
   responds, call `Pipeline.complete(response_text, session_id, token_map)` to rehydrate. Do not
   invent your own token scheme.
4. **One vault owner:** SENTINEL owns the vault. Do not add a second vault. `token_map` is the
   handshake between `sanitize` and `complete` — carry it through the request lifecycle.
5. **Valkey is a hard dependency** of the PII layer. Provide it in the dev setup (docker or a
   local instance) and document the env vars, or the gateway won't start.

## Target design (simplified — this is a demo-grade gateway, not the full platform)

Build `monoai_gateway/` with:

```
monoai_gateway/
  config.py        # env-driven settings (Valkey creds, provider choice, model map, api keys)
  pii.py           # thin async wrapper over pii_pipeline.Pipeline (to_thread sanitize/complete)
  orchestrator.py  # the reduced 9-step flow, ties PII + router + audit together
  audit.py         # append-only JSONL audit log (session_id, models, span counts, latencies)
  app.py           # FastAPI: POST /v1/chat/completions, GET /health
  __init__.py
tests/
  test_orchestrator.py   # end-to-end with StubProvider + a real Pipeline (Valkey required)
README.md          # setup, env vars, run instructions, and an honest "what's simplified" note
requirements.txt   # union of both repos' runtime deps + fastapi/uvicorn
```

**Request flow to implement in `orchestrator.py`:**

1. Normalize incoming payload (reuse the router's `RequestNormalizer`; collect user text).
2. **Scan/redact** — `await pii.sanitize(text)` → sanitized prompt + `session_id` + `token_map`.
   If any span is classified `BLOCK`, reject the request with a 4xx and audit the reason.
3. **Select model + call LLM** — pass the sanitized text through `LiteRouter.route(...)`.
4. **Rehydrate** — `await pii.complete(response.content, session_id, token_map)`; surface
   `unresolved_tokens` in the audit record if non-empty.
5. **Audit** (do this off the response path where practical) — write one JSONL line: request_id,
   session_id, difficulty, model_id, provider, span counts by label, redacted count, latencies,
   unresolved tokens.
6. Return an OpenAI-compatible response with the rehydrated content.

## Explicitly OUT of scope (stub or omit — keep it simple)

Do not build these unless a later milestone asks; leave clear TODO seams:
auth/RBAC beyond a single optional bearer key, the policy engine, semantic/exact cache,
budget enforcement, streaming, Postgres, vector store, response-side PII re-scan,
prompt-injection blocking beyond what SENTINEL already returns. Note each omission in the README.

## Milestones (do them in order, verify each before moving on)

- **M0 — Recon & setup.** Clone both repos. Confirm the API facts above against the actual
  source. Stand up Valkey. Get `pip install -e` working for both packages in one venv. Resolve
  any dependency conflicts and record them.
- **M1 — PII wrapper.** `pii.py` wrapping `Pipeline` with `asyncio.to_thread`. Prove a
  round-trip in isolation: text with an email/phone → sanitized (`[PII_TOKEN_xxxx]` present,
  original absent) → simulate an LLM echo preserving tokens → `complete()` restores the original.
- **M2 — Router wrapper.** Drive `LiteRouter` with `StubProvider`; confirm three prompts of
  increasing difficulty route to three different models. Then wire `OllamaProvider` (matches the
  local inference setup) behind a config flag.
- **M3 — Orchestrator.** Implement the full reduced flow (steps 1–6). Handle the `BLOCK` case
  and the `unresolved_tokens` case explicitly.
- **M4 — FastAPI + audit.** Expose `POST /v1/chat/completions` (OpenAI-compatible response
  shape) and `GET /health`. Emit audit JSONL. Optional single-bearer-key auth via env.
- **M5 — Tests + README.** End-to-end test with `StubProvider` + real `Pipeline`. README with
  env vars, `docker run` for Valkey, run command, and the honest "what's simplified vs the full
  MonoAI architecture" section.

## Acceptance checks (all must pass)

- `POST /v1/chat/completions` with a prompt containing an email + phone returns a coherent
  answer, and the **provider never received the raw PII** (assert against the router's log /
  the stub's captured payload).
- The rehydrated response contains the original PII values (or a documented rehydration flag if
  the model dropped a token).
- A prompt whose only sensitive content is `BLOCK`-classified is rejected with an audited reason.
- Difficulty-based routing demonstrably picks different models for simple vs complex prompts.
- The audit JSONL has one well-formed line per request with span counts and latencies.
- `README.md` states plainly which of the 9 architecture steps are real vs stubbed.

## Working style

Milestone-by-milestone, smallest working slice first. When the two repos' assumptions collide,
**stop and surface the tradeoff** rather than silently patching over it. Prefer concrete files
over prose. Do not fabricate an interface that isn't in the source — if something's missing,
say so and propose the seam.
