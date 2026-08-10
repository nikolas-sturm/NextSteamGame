# Architecture Overview

Status: draft

## System Context

NextSteamGame separates offline intelligence from online product behavior.

```text
approved upstream sources
          |
          v
Python acquisition and intelligence pipeline
          |
          v
immutable versioned build
          |
          v
Rust HTTP API and recommendation core
          |
          v
Next.js web product
```

## Ownership Boundaries

### Web

Next.js owns presentation, browser interaction, accessibility, intent view state, and rendering API results. It does not score, retrieve, interpret models, or read build artifacts directly. Generated transport types remain separate from UI view models.

### Online service

Rust owns request validation, metadata search, candidate retrieval, scoring, deterministic explanation selection, artifact compatibility checks, and operational telemetry. Normal request handling does not call Python or perform model inference.

### Recommendation core

Pure Rust code transforms normalized intent and candidate features into filtered, ranked, contribution-accounted output. It has no filesystem, network, database, clock, or random dependency. Stable tie-breaking is part of behavior.

### Offline pipeline

Python owns upstream acquisition, review processing, classification, semantic extraction, canonicalization, embedding, candidate generation, evaluation orchestration, and artifact publication. Each stage writes new outputs and preserves source lineage.

### Artifact store and retrieval

Runtime readers validate immutable builds and expose metadata, candidate edges, vector retrieval, and evidence by typed interfaces. Candidate graph serves normal requests. Dynamic vector retrieval handles intents whose coverage cannot be trusted statically.

## Planned Repository Shape

```text
apps/web/                       Next.js product
services/api/                   Axum service
crates/domain/                  shared Rust domain types
crates/recommendation-core/     pure ranking and explanation policy
crates/artifact-store/          immutable build readers
crates/retrieval/               graph and vector retrieval abstractions
pipeline/src/nextsteam_pipeline/ offline data and ML stages
schemas/api/                    source API contract
schemas/artifacts/              artifact contracts
schemas/events/                 telemetry and optional event contracts
evaluation/                     versioned judgments, runners, and reports
infra/                          containers and deployment definitions
tools/                          repository automation
```

## Online Request Flow

1. API validates and normalizes request against configuration limits.
2. Retrieval selects static graph, dynamic vector, or declared fallback mode.
3. Artifact store hydrates compact features required by scorer.
4. Recommendation core applies filters, calculates contributions, and uses stable tie-breaking.
5. Explanation selector returns strongest supported factors and evidence IDs.
6. API hydrates public game metadata and returns build ID, normalized intent, retrieval state, results, and typed degradation.

## Offline Build Flow

1. Acquire fresh upstream metadata and review evidence with source timestamps.
2. Store raw records without silent reinterpretation.
3. Filter and classify evidence through versioned stages.
4. Extract lane semantics and link every interpreted concept to evidence.
5. Canonicalize concepts through reviewed, versioned mappings.
6. Generate embeddings and independent retrieval neighborhoods.
7. Build candidate features, runtime graph, metadata, and evidence artifacts.
8. Evaluate retrieval, ranking, explanation integrity, throughput, and resource use.
9. Publish complete directory with manifest and checksums only after validation passes.

## Runtime Rules

- Builds mount read-only and never mutate after publication.
- Service fails readiness for unsupported schemas, incompatible API versions, or checksum mismatch.
- Build activation uses a versioned mount or atomic pointer change.
- Current and previous compatible builds remain deployable.
- Postgres is absent until a mutable requirement such as feedback or accounts justifies it.
- Free-text user content is not logged by default.

## Contract Workflow

API and artifact schemas are authored before consumers. OpenAPI generates TypeScript transport types. Binary artifact formats require explicit schema versions, compatibility tests, and corruption tests. Domain and UI models do not import generated transport types as internal state models.
