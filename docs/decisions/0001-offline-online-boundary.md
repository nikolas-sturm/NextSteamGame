# ADR-0001: Separate Offline Intelligence From Online Recommendation Behavior

Status: accepted

Date: 2026-08-10

## Context

Acquisition, classification, semantic extraction, embeddings, and graph construction need Python's data and ML ecosystem. Online recommendation requests need deterministic behavior, low latency, bounded resources, and straightforward operations. Runtime model inference would couple availability and latency to large model infrastructure while making explanations harder to reproduce.

## Decision

Python owns offline acquisition, intelligence, evaluation orchestration, and artifact publication. Rust owns online retrieval, scoring, explanation selection, and HTTP behavior. Next.js owns presentation only.

Normal online requests consume precomputed immutable artifacts and perform no model inference. Dynamic vector retrieval may query a prebuilt index but remains separate from scoring policy.

## Consequences

- Build publication becomes an explicit product interface.
- Online service can run without Python, model weights, GPU access, or mutable database.
- New model output reaches production through a versioned build rather than hidden runtime change.
- Free-text and multi-seed retrieval require precomputed vector infrastructure or a separately approved inference design.
- Cross-language contracts require schema and compatibility testing.

## Verification

- Integration test starts API with only service binary and one valid build.
- Network and process controls prove normal recommendation path cannot call Python or model services.
- Deterministic replay returns same ordered result for identical request and build.
