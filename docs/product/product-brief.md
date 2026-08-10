# Product Brief

Status: draft

## Problem

Storefront genres and popularity signals often describe audience or market category, not why a player values a game. Players seeking a specific mechanic, emotional tone, narrative form, or gameplay loop must inspect many weak matches and cannot tell why a recommendation appeared.

## Promise

NextSteamGame helps a player express which qualities matter and returns ranked games with deterministic, auditable reasons.

## Target Users

### Intent-led explorer

Knows a specific quality worth repeating, such as a progression loop, decision structure, atmosphere, or unusual mechanic. Needs controls that preserve this intent instead of broadening it into genre similarity.

### Niche hunter

Values a rare combination poorly represented by storefront tags. Needs identity concepts, niche anchors, and evidence that a result contains the claimed quality.

### Curious chooser

Starts from a liked game but cannot yet name why it worked. Needs clear choices, progressive detail, and examples that help form intent without requiring recommendation-system vocabulary.

### Deliberate evaluator

Wants to compare plausible games before leaving for Steam. Needs concise metadata, tradeoffs, confidence, and reasons strong enough to judge fit.

## Jobs To Be Done

1. When I finish or enjoy a game for a particular reason, help me find another game that preserves that reason rather than only its genre.
2. When several qualities mattered differently, let me state their relative importance and see results respond.
3. When a recommendation looks surprising, show evidence-backed reasons so I can decide whether it is insightful or wrong.
4. When recommendations drift, let me refine or exclude concepts without restarting.
5. When I find a useful intent, let me share it without requiring an account where practical.

## MVP Journey

1. Search for one Steam game.
2. Review a simple set of inferred qualities.
3. Select valued qualities and adjust four semantic lanes: mechanics, narrative, vibe, and structure or loop.
4. Optionally include or exclude identity concepts and niche anchors.
5. Review ranked results with score contributions, concise explanations, evidence, and useful Steam metadata.
6. Refine intent and rerank immediately.
7. Open a result on Steam or share stable intent.

## Functional Requirements

- Search and select one Steam seed game.
- Represent intent independently from UI and transport state.
- Permit zero emphasis for an irrelevant semantic lane.
- Validate weights, exclusions, limits, and unsupported concepts.
- Keep advanced concept controls discoverable but secondary.
- Return stable ordering for identical intent and build.
- Explain every result from score contributions and identified evidence.
- Expose reduced confidence when evidence or retrieval coverage is weak.
- Keep quality and popularity signals distinct from semantic identity.
- Support keyboard-complete use at narrow mobile and wide desktop sizes.

## Non-Goals

First launch excludes accounts, saved searches, social features, ownership sync, native mobile apps, collaborative filtering, runtime LLM explanations, real-time training, marketplace features, serverless recommendation execution, and an administrative CMS.

Multiple positive seeds, negative seeds, free-text intent, comparison, and relevance feedback remain post-MVP unless needed to validate transport extensibility.

## Product Constraints

- New users receive value without registration.
- Product language describes player intent, not embeddings or vector databases.
- Normal online requests perform no model inference.
- Rust owns online recommendation behavior.
- Production artifacts load read-only and identify their build.
- No compatibility with previous UI, API, data, or behavior is required.

## Success Measures

Initial thresholds will be set from fresh baseline measurements. Launch evidence must include:

- Task-completion and comprehension tests for search, intent editing, reasons, and refinement
- Human pairwise relevance and nDCG evaluation
- Candidate coverage under default and extreme lane weights
- Explanation evidence precision and contribution reconciliation
- Mobile performance and accessibility validation
- Measured warm API latency, memory use, and deterministic replay

Clicks alone are not a relevance measure because artwork, familiarity, price, and popularity confound them.
