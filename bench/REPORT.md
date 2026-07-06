# MonoAI Gateway 2.0 — Bench Report

Generated: 2026-07-06T16:57:41.868425+00:00


See `DECISIONS.md` for the honest caveats on corpus size/curation and the TF-IDF-classifier-instead-of-transformer substitutions behind these numbers.


### PII detection (EN, bench/corpora/en_pii.jsonl -- see DECISIONS.md for corpus size caveat)

| Label | Precision | Recall | F1 | vs. Presidio |
|---|---|---|---|---|
| ADDRESS | 1.00 | 1.00 | 1.00 | not run |
| CREDIT_CARD | 1.00 | 1.00 | 1.00 | not run |
| DATE_TIME | 1.00 | 1.00 | 1.00 | not run |
| EMAIL | 1.00 | 1.00 | 1.00 | not run |
| GOV_ID | 1.00 | 1.00 | 1.00 | not run |
| IP_ADDRESS | 1.00 | 1.00 | 1.00 | not run |
| PERSON | 1.00 | 1.00 | 1.00 | not run |
| PHONE | 1.00 | 1.00 | 1.00 | not run |
| SECRET | 1.00 | 1.00 | 1.00 | not run |
| USERNAME | 1.00 | 1.00 | 1.00 | not run |

### Router accuracy (bench/corpora/routing_labeled.jsonl, n=120 -- see DECISIONS.md for corpus size caveat)

| Stage | Accuracy | p95 latency |
|---|---|---|
| Heuristic only | 0.90 | n/a |
| Cascade (+ classifier) | 1.00 | 0.43ms |


### Gateway end-to-end latency (StubProvider, n=50 sequential requests)

| Percentile | Latency |
|---|---|
| p50 | 89.89ms |
| p95 | 101.34ms |
| p99 | 110.66ms |


### Cross-runner synthetic benchmark (bench/harness.py)

> portkey_mock/litellm_mock/lakera_mock/protecto_mock are NOT the real vendor products -- no API access/keys/license for any of them exists in this environment. Each is a small, independently-written stand-in reflecting only that product's public positioning (see bench/harness.py's module docstring and DECISIONS.md). Latency numbers are real measured execution time of each mock's own code; the mock's detection LOGIC is illustrative, not a competitive benchmark of the named product.

| Runner | p50 ms | p99 ms | throughput req/s | PII recall | injection recall | FP labels |
|---|---|---|---|---|---|---|
| monoai | 0.420 | 0.873 | 2714.17 | 1.00 | 1.00 | none |
| portkey_mock | 0.000 | 0.001 | 1496951.66 | 0.00 | 0.00 | none |
| litellm_mock | 0.000 | 0.000 | 2003144.33 | 0.00 | 0.00 | none |
| lakera_mock | 0.002 | 0.004 | 419770.96 | 0.00 | 0.50 | none |
| protecto_mock | 0.003 | 0.006 | 283669.17 | 0.31 | 0.00 | none |
