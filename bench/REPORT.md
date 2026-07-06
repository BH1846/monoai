# MonoAI Gateway 2.0 — Bench Report

Generated: 2026-07-06T07:18:41.946783+00:00


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
| Cascade (+ classifier) | 1.00 | 0.39ms |


### Gateway end-to-end latency (StubProvider, n=50 sequential requests)

| Percentile | Latency |
|---|---|
| p50 | 89.92ms |
| p95 | 106.19ms |
| p99 | 109.60ms |

