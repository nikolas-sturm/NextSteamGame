# Artifact Schemas

Artifact schema version `1` defines thin-slice runtime JSON plus source Parquet and metadata SQLite. Runtime readers fail closed on unknown versions or checksum mismatch.

Required runtime files:

- `manifest.json`
- `metadata.json`
- `graph.json`
- `evidence.json`

Required source and analysis files:

- `metadata.sqlite`
- `source/games.parquet`
- `source/reviews.parquet`
- `source/identity.parquet`
- `source/candidate_edges.parquet`
- `source/explanation_evidence.parquet`

Binary graph, offsets, and evidence files may be added under artifact schema version `2` after measured layout benchmarks. Format optimization cannot silently change v1 semantics.
