# Human Relevance Evaluation Protocol

Status: draft

## Purpose

Measure whether v2 recommendations preserve qualities players explicitly value. Evaluation establishes an independent target; previous product output is not a baseline or source of judgments.

## Provenance

All queries, candidate pools, labels, guidance examples, and reports must be newly authored for v2. Evaluators may use approved upstream game information and retained source evidence. Each dataset release records authorship, source window, ontology version, and change history.

No legacy recommendation, fixture, mapping, generated analysis, or project-specific model output may seed an evaluation set.

## Evaluation Units

Corpus must cover:

- Single-game general relevance
- Mechanics-only, narrative-only, vibe-only, and structure or loop-only intent
- Extreme lane weights
- Identity concept and niche-anchor intent
- Negative constraints
- Sparse-review seeds and candidates
- Popularity-bias probes
- Diversity and redundancy
- Explanation correctness
- Future free-text and multi-seed queries

Each query includes normalized intent, a plain-language rationale for why that intent matters, eligibility rules, and independently sourced context sufficient for judgment.

## Judgment Tasks

### Pointwise relevance

Rate candidate fit to stated intent:

- `3`: strong match on valued qualities; no material contradiction
- `2`: useful match with one meaningful limitation
- `1`: weak or surface-level match
- `0`: irrelevant or contradicted by intent
- `U`: insufficient evidence to judge

Evaluator records confidence and short evidence reference. `U` remains missing judgment, not zero relevance.

### Pairwise preference

Given one intent and two eligible candidates, select stronger fit, tie, or insufficient evidence. Artwork prominence, price, popularity, and familiarity should not influence semantic relevance judgment.

### Explanation audit

For each public claim, determine:

- Evidence resolves and supports claim.
- Contribution direction and magnitude category agree with scoring output.
- Missing-data or reduced-confidence language is present when required.
- Explanation omits unsupported certainty.

Any fabricated or contradicted material claim is a critical integrity failure.

## Collection Procedure

1. Train evaluators on newly authored examples not included in measured set.
2. Blind candidate rank, score, retrieval lane, and popularity where task permits.
3. Randomize candidate order and pair orientation.
4. Require two independent judgments for development sets and three for held-out launch sets.
5. Adjudicate material disagreement without exposing system identity.
6. Track inter-rater agreement and reasons for disagreement.
7. Freeze versioned releases before tuning against them.

## Dataset Splits

- Development set supports iteration and failure analysis.
- Validation set supports policy and hyperparameter selection.
- Held-out launch set is opened only for declared release candidates.
- Challenge set contains rare, sparse, adversarial, and extreme-intent cases and is always reported separately.

Games or near-duplicate query formulations should not cross splits when leakage would inflate results.

## Metrics

Report at minimum:

- Recall@K and retrieval recall against exhaustive samples
- nDCG@K
- Mean reciprocal rank where one early strong match matters
- Pairwise preference win rate with ties and uncertainty shown
- Candidate graph coverage by intent class
- Explanation evidence precision and critical-failure count
- Exposure by popularity band and result redundancy
- Response latency and memory for same evaluated workload

Every aggregate includes query count, judgment coverage, uncertainty interval, and slice breakdown. Retrieval misses and ranking failures remain separate.

## Change Control

Evaluation data, scorer configuration, artifact Build ID, and report code revision form one report identity. Corrections create a new dataset version with rationale. Results cannot be compared across changed judgments without explicit qualification.

## Privacy and Safety

Do not collect player accounts, private library data, or free-text personal information for baseline evaluation. Remove evaluator personal data from published reports. Approved public game evidence can be retained according to source terms and documented retention policy.

## Launch Gate

Numeric thresholds remain unset until baseline runs establish difficulty and variance. Launch requires approved thresholds for human relevance, candidate coverage, explanation integrity, bias slices, determinism, latency, and memory, plus qualitative review of major misses.
