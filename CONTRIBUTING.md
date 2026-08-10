# Contributing to NextSteamGame v2

## Clean-Room Requirement

Every contribution must be independently authored for v2. This repository history, source tree, and build lineage must remain separate from the legacy product.

Allowed references:

- Public upstream documentation and APIs
- Public third-party packages and pretrained models
- Steam appids and Steam-hosted media URLs
- Plain-language observations about user problems, domain needs, upstream constraints, and failure cases
- Product concepts explicitly adopted in v2 requirements

Forbidden inputs:

- Legacy source, components, styles, assets, tests, manifests, or deployment files
- Legacy API contracts, database schemas, recommendation formulas, constants, or defaults
- Legacy prompts, extraction schemas, mappings, checkpoints, embeddings, candidate graphs, or generated analyses
- Legacy databases, fixtures, or build artifacts
- Translated, mechanically rewritten, or templated versions of any forbidden input

Never merge the legacy branch, cherry-pick a legacy commit, restore a legacy path into this branch, or add a legacy subtree. Do not use legacy screenshots or interface structure as design input.

## Reference Method

When legacy inspection is necessary:

1. Record only problem, constraint, or observed behavior.
2. Close the reference.
3. Label the note as `Observation`, `Hypothesis`, or `Decision`.
4. Write an original requirement or test case from user need.
5. Design and implement from that written requirement.

## Data Provenance

Production data must originate from approved upstream sources through v2 pipeline code. Every interpreted concept must retain evidence lineage. Raw, interpreted, canonical, embedded, and published stages remain separate. Published artifacts are immutable.

Do not commit acquired datasets, model weights, embeddings, local builds, credentials, or user-provided content.

## Engineering Rules

- Prefer minimal, typed interfaces between product layers.
- Keep recommendation-core deterministic and free of I/O.
- Account for each score-affecting policy through a contribution or explicit filter.
- Treat missing data, numeric precision, rounding, and tie-breaking as explicit policies.
- Author API schemas before generated clients or handlers.
- Add tests from v2 requirements and fresh evaluation judgments.
- Benchmark sequential scoring before introducing parallelism.
- Avoid logging free-text intent or other user content by default.

## Change Review

Every pull request must confirm:

- Work was authored from v2 requirements, not legacy implementation.
- No forbidden file, snippet, schema, prompt, asset, or generated artifact was reused.
- New data inputs have documented provenance.
- Contract changes update source schemas before generated code.
- Behavioral changes include appropriate tests or evaluation cases.
- Security, privacy, accessibility, and operational effects were considered.
