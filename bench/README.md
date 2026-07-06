Reproducible benchmark harness (G15). `make bench` (== `uv run python bench/run_all.py`) writes `bench/REPORT.md` and `bench/results/latest.json`:

- `run_pii_bench.py` — precision/recall/F1 per PII label on `corpora/en_pii.jsonl`.
- `run_router_bench.py` — heuristic vs. cascade accuracy on `corpora/routing_labeled.jsonl` (`--train` retrains the classifier first).
- `run_latency_bench.py` — end-to-end p50/p95/p99 through the orchestrator with `StubProvider`.
- `harness.py` (Phase 4) — p50/p99 latency, throughput (req/s), PII recall, and per-label false-positive
  splits for MonoAI's real pipeline against four **mock** baseline runners loosely modeled on the public
  positioning of Portkey, LiteLLM, Lakera, and Protecto. **These are NOT the real vendor products** — see
  the module's own docstring and DECISIONS.md before citing any number from `bench/results/latest.json`.

**Honest caveat** (see `DECISIONS.md`): the corpora here are small,
programmatically-generated starter sets (`generate_*_corpus.py`), not the
production-curated corpora (300+ real attacks, ai4Privacy-scale PII
benchmarks) the master plan calls for — that curation is explicitly
human time, not something an agent session substitutes for. No Presidio
comparison is run in this pass (would add a new dependency/setup step).
