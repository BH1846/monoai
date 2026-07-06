Reproducible benchmark harness (G15). `make bench` (== `uv run python bench/run_all.py`) writes `bench/REPORT.md`:

- `run_pii_bench.py` — precision/recall/F1 per PII label on `corpora/en_pii.jsonl`.
- `run_router_bench.py` — heuristic vs. cascade accuracy on `corpora/routing_labeled.jsonl` (`--train` retrains the classifier first).
- `run_latency_bench.py` — end-to-end p50/p95/p99 through the orchestrator with `StubProvider`.

**Honest caveat** (see `DECISIONS.md`): the corpora here are small,
programmatically-generated starter sets (`generate_*_corpus.py`), not the
production-curated corpora (300+ real attacks, ai4Privacy-scale PII
benchmarks) the master plan calls for — that curation is explicitly
human time, not something an agent session substitutes for. No Presidio
comparison is run in this pass (would add a new dependency/setup step).
