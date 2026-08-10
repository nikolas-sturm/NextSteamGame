# ADR-0003: Author API Schemas Before Implementations

Status: accepted

Date: 2026-08-10

## Context

Web and API development proceed in different languages. Hand-maintained duplicate request and response models drift, while importing transport models throughout UI state couples product behavior to wire format.

## Decision

OpenAPI is the source contract for HTTP endpoints, validation shapes, response variants, and typed errors. TypeScript transport types are generated from committed schemas. Rust handlers must prove conformance through tests or generation tooling selected during foundation work.

UI view models and Rust domain models remain explicit internal types. Conversion at boundaries prevents generated transport structure from becoming application architecture.

## Consequences

- Contract changes begin under `schemas/api` and receive compatibility review.
- Generated files are reproducible and never edited by hand.
- CI detects stale generated output.
- Conversion code is required at web and API boundaries.
- API versioning reflects public behavior, not internal model revisions.

## Verification

- CI regenerates or checks generated TypeScript output.
- Contract tests cover valid, invalid, degraded, and error responses.
- Internal UI state has no dependency on generated transport behavior beyond boundary adapters.
