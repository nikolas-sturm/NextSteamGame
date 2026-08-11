# Evaluation Reports

Reports preserve measured local or upstream evidence. They do not establish launch acceptance unless the evaluation protocol defines and approves a threshold.

| Report | Scope | Result |
| --- | --- | --- |
| `upstream-100-2026-08-10.json` | Fresh thin slice | 95 games; integrity passed; graph source coverage 1.0. |
| `scale-500-audit-after-smoke.json` | Exact 500-game immutable release | 123,045 edges; 1,219 evidence records; checksums passed after API smoke. |
| `scale-2000-audit-after-smoke.json` | Exact 2,000-game immutable release | 842,728 bounded edges; 5,400 evidence records; checksums passed after API smoke. |
| `candidate-graph-scale-2000.json` | Exhaustive candidate comparison | Recall@10: 0.9508 at 500, 0.9230 at 1,000, 0.9092 at 2,000. |
| `zvec-local-1000.json` | Deterministic 512-dimensional vectors | Flat and HNSW Recall@10 1.0; local build/query timings included. |
| `api-load-scale-500.json` | 1,000 requests, concurrency 25 | Zero errors; graph mode; local p95 89.99 ms. |
| `api-load-scale-2000.json` | 1,000 requests, concurrency 25 | Zero errors; graph mode; local p95 122.87 ms. |
| `api-load-dynamic-fixture.json` | 500 requests, concurrency 16 | Zero errors; dynamic-vector mode; test fixture only. |
| `fixture-dynamic-audit-after-smoke.json` | Dynamic-vector mutation check | Fixture source checksums passed after runtime access. |
| `core-proptest-10000.json` | Rust scorer properties | 10,000 cases per property; zero failures. |

## Limits

- Candidate recall uses deterministic exhaustive ranking, not human relevance judgments.
- Zvec benchmark inputs and dynamic fixture are synthetic and make no product-quality claim.
- Local latency excludes production network, proxy, container, and host variance.
- Coverage metrics do not prove semantic correctness or explanation support.
- GPU model, moderated research, private alpha, and production operations remain unexecuted external gates.
