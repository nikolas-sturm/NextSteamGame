# Contract And Build Versioning

## API

OpenAPI document under `schemas/api/openapi.yaml` is source contract. Compatible additive changes retain major path version. Removing fields, narrowing accepted values, or changing semantics requires new major path.

Generated clients are reproducible outputs. Internal Rust, Python, and UI models convert at boundaries and do not treat transport types as domain architecture.

## Artifacts

`artifact_schema_version` changes when runtime readers need different file names, encodings, or field semantics. Readers accept only explicitly supported versions. `api_compatibility_version` declares which API behavior artifact can support.

Published build never mutates. Corrected data receives new Build ID even when schema stays same.

## Models And Ontology

Model ID includes provider, family, revision, instruction, dimensions, dtype, and relevant preprocessing. Ontology version identifies exact canonical mapping release. Either change creates new Build ID.

## Events

Telemetry contracts version independently. User-provided free text is excluded from request telemetry. Collection and retention require explicit privacy decision before feedback or accounts launch.
