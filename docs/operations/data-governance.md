# Data Governance

## Approved Inputs

V2 acquires public game metadata, public Steam review text, and approved aggregate catalog signals directly from upstream services. Builds never ingest legacy databases, mappings, prompts, embeddings, or generated outputs.

## Review Evidence

Review evidence exists to support semantic interpretation and explanation audits. Acquisition stores no author account ID, profile URL, display name, device identifier, or private library data. Review ID remains only for upstream deduplication and provenance. Playtime is retained only as source-quality context and is not exposed online.

Public runtime evidence contains at most 500 characters, source category, game appid, and opaque Evidence ID. It must not expose reviewer identity or imply one review represents consensus.

## Retention

Published build directories are immutable, but storage retention is finite. Current and previous deployable builds remain available; older source snapshots and review evidence follow source terms, research need, and documented deletion schedule. Deleting an expired whole build is permitted. Mutating files inside a retained build is not.

Before production acquisition, owner must record source terms, allowed retention, deletion cadence, access boundary, and incident contact. Feedback or accounts require separate privacy decision and retention policy.

## Access

Runtime service receives only public metadata, candidate features, and bounded evidence excerpts. Raw review Parquet remains offline, access-controlled, and absent from web/API containers. Logs exclude review text and user free-text intent by default.
