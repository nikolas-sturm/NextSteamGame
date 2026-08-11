# Roadmap Status

Updated: 2026-08-11

| Phase | Implementation status | Remaining acceptance evidence |
| --- | --- | --- |
| 0. Orphan foundation | Implemented | Repository default branch changes only after launch acceptance. |
| 1. Independent specification | Implemented | Product thresholds finalized from human research measurements. |
| 2. Monorepo foundation | Locally verified | Linux container builds confirmed by CI or an active Docker daemon. |
| 3. Thin data slice | Measured upstream baseline | A 95-game release and exact 500- and 2,000-game releases passed artifact audit; human semantic-quality thresholds remain unset. |
| 4. Ontology, classification, embeddings | Deterministic baseline measured | Newly authored labels and judgments, cached GPU model runs, VRAM measurements, and model selection remain external hardware/research gates. Local Zvec flat and HNSW benchmark reached Recall@10 1.0 on 1,000 deterministic vectors. |
| 5. Candidate graph and Rust core | Measured local baseline | Exhaustive Recall@10 is 0.9508, 0.9230, and 0.9092 at 500, 1,000, and 2,000 games. Python binding and 10,000-case property run pass. Approval thresholds remain unset. |
| 6. Rust API runtime | Measured local baseline | Graph and dynamic-vector smoke pass with post-run checksum audit. Local concurrent runs had zero errors; production host, Linux container, memory, and approved latency gates remain. |
| 7. Web and design system | Build and tests verified | Three-direction moderated comparison, screen-reader audit, and deployed API-backed E2E require participants or deployment access. |
| 8. Full-catalog pipeline | 2,000-game stage verified | Exact 500 and 2,000 acquisition/build stages pass. 5,000, 20,000, and full stages require broader upstream acquisition and execution time. |
| 9. Integrated alpha | Not executed | Private participants, human relevance judgments, explanation audits, and tuning report require approved study access. |
| 10. Production launch | Infrastructure draft | Host, TLS/proxy, dashboards, alerts, staged rollout, rollback drill, and launch acceptance require production access. |

Measured reports are indexed in [evaluation/reports](../evaluation/reports/README.md). Implementation status never substitutes for measured quality, human review, upstream acquisition, GPU execution, or production operations.
