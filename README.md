# MonoAI Gateway 2.0

A sovereignty-grade AI data firewall: an LLM gateway with reversible PII
tokenization, declarative policy governance, per-key auth/budgets/rate
limits, provider fallback chains, streaming, and a tamper-evident audit
chain.

This is **Phase 1 ("Gateway Core")** of a 4-phase build. See
`monoai-gateway-2.0-master-plan.md` for the full plan and gap register,
and `DECISIONS.md` for every deviation/simplification made along the way.

## Phase 1 status — gap register

| Gap | What closes it | Proof |
|---|---|---|
| G1 (streaming) | `gateway/streaming.py` sliding-window rehydrator | `tests/integration/test_streaming.py` |
| G2 (per-key auth) | `gateway/auth/` virtual keys, budgets, rate limits | `tests/integration/test_auth.py` |
| G3 (policy) | `core/policy/` declarative YAML engine | `tests/integration/test_policy.py` |
| G5 (output scan) | `PiiEngine.scan_output` before rehydration | `tests/integration/test_output_scan.py` |
| G6 (fallback) | `gateway/providers/fallback_chain.py` + circuit breaker | `tests/integration/test_fallback.py` |
| G8 (multi-turn) | `core/vault/session_tokens.py` value-deterministic tokens | `tests/integration/test_multiturn.py` |
| G14 (secrets hygiene) | gitignored `.env`, CI gitleaks job | `tests/unit/test_repo_hygiene.py` |

G4/G7/G9-G13/G15/G16 (injection detection, embedding router, observability,
tamper-evident signing, Postgres backends, Gulf/Arabic pack, benchmarks,
file scanning, MCP firewall) are Phase 2-4 — see the placeholder
`README.md` in `ner-sidecar/`, `filescan-worker/`, `mcp-firewall/`, `bench/`,
and `core/detect/packs/gulf_ar/`.

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
  api/           chat, health, evidence, admin (key/policy CRUD), files (Phase 3 stub)
  auth/          virtual keys, token-bucket rate limiter, budget checks
  providers/     OpenAI-compatible / Ollama / stub adapters, circuit breaker, fallback chain
  router/        request normalizer (4 wire formats) + heuristic difficulty classifier
  pii.py         role-preserving sanitize / output-scan / rehydrate glue
  orchestrator.py the 6-step request spine
  streaming.py   SSE sliding-window rehydrator
policies/        default.yaml, finance_strict.yaml, gulf_sovereign.yaml (Phase 1 stub)
tests/           unit/ integration/ adversarial/ e2e/
scripts/         verify_audit_chain.py — standalone verifier to hand to auditors
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

Phase 1 — Gateway Core: done (all 7 gaps closed, 175 tests green)
Gap	Status	Proof
G1 streaming	✅ closed	test_streaming.py — sliding-window rehydrator, token-split-across-chunks + TTFB tests pass
G2 per-key auth	✅ closed	test_auth.py — virtual keys, budgets, rate limits, model allowlist all pass
G3 policy	✅ closed	test_policy.py — declarative YAML engine, same prompt/two policies/two outcomes
G5 output scan	✅ closed	test_output_scan.py — model-leaked SSN redacted before it reaches the client
G6 fallback/circuit breaker	✅ closed	test_fallback.py — primary→secondary, all-down→503, breaker opens after N failures
G8 multi-turn	✅ closed	test_multiturn.py — same email→same token across turns, roles preserved to provider
G14 secrets hygiene	✅ closed	test_repo_hygiene.py + CI gitleaks job; Valkey password rotated, .env.example clean
Plus the carried-forward 7-test regression suite and the adversarial rehydration-safety property test (BLOCK values never leak) — all passing. Verified live end-to-end against real Valkey (not just mocked): health checks, key creation, streaming/non-streaming chat, BLOCK rejection, rate limiting, and audit-chain continuity across a real server restart.

Found and fixed 4 real bugs during live testing (not just unit tests) that unit tests alone hadn't caught — difficulty-classifier token inflation, ONNX NER false positives on token brackets and small streaming windows, an off-by-one in the streaming split logic, and audit-chain resume across restarts. Each has a dedicated regression test now.

Phase 2 — Detection depth (G4, G7, G9, G10, G11, G12, G15): not started
No ner-sidecar, injection detection, Gulf/Arabic pack, embedding router, OTel/Prometheus, Ed25519 signing, Postgres backends, or bench/ harness. Placeholder dirs with .gitkeep + README only.

Phase 3 — File/media scanning (G16): not started
filescan-worker/ is an empty placeholder; POST /v1/files/scan returns 501.

Phase 4 — MCP firewall (G13): not started
mcp-firewall/ is an empty placeholder.


