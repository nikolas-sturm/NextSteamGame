# Recommendation Quality Hypotheses

Status: draft

These hypotheses define questions for fresh evaluation. They do not prescribe scoring constants.

| ID | Hypothesis | Evidence needed |
| --- | --- | --- |
| QH-01 | Separating mechanics, narrative, vibe, and structure or loop improves relevance when players value one aspect strongly. | Human judgments for lane-isolated and extreme-weight queries compared with fused retrieval. |
| QH-02 | Canonical identity concepts recover meaningful matches missed by vector similarity alone. | Pairwise judgments and candidate recall for identity-focused queries. |
| QH-03 | Niche anchors improve precision for rare mechanics or structures when supported by strong evidence. | Anchor-specific precision, miss analysis, and evidence audits. |
| QH-04 | A union of independent retrieval lanes protects recall better than one default fused neighborhood. | Recall against exhaustive samples at several candidate graph sizes. |
| QH-05 | Keeping popularity separate from semantic fit increases discovery without unacceptable quality loss. | Relevance, catalog exposure, popularity distribution, and pairwise preference comparisons. |
| QH-06 | Explicit negative constraints improve control only when applied as visible filters or fully accounted penalties. | Constraint satisfaction rate, no-result rate, and user comprehension tests. |
| QH-07 | Contribution-backed explanations increase trust calibration more than generic similarity statements. | Explanation correctness, evidence precision, comprehension, and calibrated confidence surveys. |
| QH-08 | Stable deterministic ordering helps users understand refinement effects. | Replay tests and task studies comparing intent changes with ranking changes. |
| QH-09 | Sparse-evidence disclosure prevents overclaiming without making viable recommendations unusable. | Claim audits and usability tests across sparse-review games. |
| QH-10 | Controlled diversity improves useful discovery after top semantic matches without damaging early-rank relevance. | nDCG, subtopic coverage, redundancy, and pairwise preference by rank band. |

## Evaluation Discipline

- Tune only against versioned v2 judgments.
- Keep development and held-out query sets separate.
- Record retrieval misses separately from ranking errors.
- Compare changes against declared baselines and confidence intervals.
- Inspect failures qualitatively; aggregate metrics cannot establish hidden identity fit alone.
- Reject policies whose explanation cannot reconcile with scoring behavior.
