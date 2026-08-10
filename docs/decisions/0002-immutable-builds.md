# ADR-0002: Publish Immutable, Self-Describing Builds

Status: accepted

Date: 2026-08-10

## Context

Recommendation results depend on metadata, model configuration, ontology, embeddings, candidate features, evidence, and scorer compatibility. Partial updates or in-place mutation can produce unreproducible rankings and invalid explanations.

## Decision

Each publication creates a complete directory identified by Build ID. Manifest records schema and API compatibility versions, source and pipeline revisions, acquisition windows, model configuration, ontology and scorer versions, counts, checksums, and evaluation report identity.

Published directories never mutate. Service validates required files, checksums, versions, and structural invariants before readiness. Activation selects a whole validated build through versioned mount or atomic pointer.

## Consequences

- Publication requires temporary storage for complete builds.
- Current and previous production builds remain available for rollback.
- Build ID can explain and replay recommendation behavior.
- Failed or interrupted publication cannot expose a partial build.
- Artifact schema evolution needs explicit compatibility policy.

## Verification

- Mutation after publication is rejected operationally.
- Missing, corrupt, or incompatible files keep service unready.
- Rollback test switches service and artifacts to previous build as one operation.
- Recommendation and health responses expose active Build ID.
