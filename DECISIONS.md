# Decisions log

Deviations from the master plan / Phase 1 plan, with rationale. Append, don't rewrite history here.

## Step 0 — Repo transform

- **Not rewriting git history.** The Valkey password committed in `README.md` (HEAD) and in the `SENTINEL-2.0` submodule's own upstream `.env` stays in history. It has been rotated (dead credential), so the residual exposure is accepted rather than doing a destructive `filter-repo` + force-push without explicit user sign-off.
- **Submodules deinit'd and absorbed.** `SENTINEL-2.0` and `Lite_Multimodel_switching` are no longer git submodules. Their logic is copied/adapted into `core/` and `gateway/`. Full read-only reference checkouts of both live at `/home/dk/monoai-port-reference/` (outside this repo) for the duration of the porting work.

## Step 1 — Scaffold

- **Top-level import namespace, not `core.*`-nested.** `core/`'s sub-packages (`contracts`, `detect`, `policy`, `vault`, `audit`) are installed as flat top-level Python packages (`import contracts`, `import detect.pipeline`, etc.), not nested under a `core.` namespace. This matches the approved directory tree exactly (`core/contracts/`, `core/detect/`, ... directly under the workspace-member directory) without introducing a redundant nested `core/core/` src-layout directory. Likewise `gateway/`'s pieces (`app`, `config`, `api`, `auth`, `streaming`, `router`, `providers`) are flat top-level modules. This mirrors how the pre-rewrite codebase already resolved `monoai_gateway`/`monoai_router`/`pii_pipeline` as flat top-level packages.
- **Secrets stage split from regex stage.** `SENTINEL-2.0/pii_pipeline/rampart/regex.py`'s `_detect_secrets`/`_SECRET_PATTERNS`/`_PASSWORD_CUE_RE` move to their own `core/detect/stages/secrets_stage.py` rather than staying fused inside `regex_stage.py`, so secrets detection gets its own detector-version string for audit attribution (a sovereignty-relevant surface worth tracking independently).
- **Hash-chaining implemented in Phase 1, not deferred.** `core/audit/chain.py`'s `compute_hash`/`append`/`verify` are real in Phase 1 (cheap to implement, and invariant #2 — "chain to the previous record's hash" — applies to all of Phase 1). Only the Postgres/webhook sinks and the Ed25519-signed evidence export layer defer to Phase 2.
- **SQLite before Postgres, for both vault and auth key storage.** `core/vault/storage/postgres_store.py` and a `PostgresKeyStore` in `gateway/auth/` are stubs (`NotImplementedError`) in Phase 1; SQLite backs both. Rate-limit counters use Valkey (already a hard dependency for the vault master key), reused under a separate key namespace — no new infra introduced for Phase 1.
- **Negation override moves from detection to policy.** `locked_spans.py`'s old behavior of setting `override_classification="PRESERVE"` directly is replaced: `core/detect/stages/locked_span_stage.py` now only attaches `span.meta["negated"] = True`; the actual PRESERVE override is applied by `core/policy/engine.py`'s `overrides.locked_span_negation` rule, per the mission's explicit instruction that action-assignment moves out of detectors into policy.
