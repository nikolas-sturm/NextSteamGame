# Incident Runbook

## First Response

1. Identify active service revision and Build ID.
2. Preserve request IDs and typed error categories; do not collect intent text.
3. Determine whether fault is process, artifact, upstream proxy, capacity, or contract mismatch.
4. Stop rollout when error or integrity threshold is exceeded.
5. Roll back service and artifact together when compatibility is uncertain.

## Artifact Failure

Checksum, schema, duplicate identity, or structural failure must keep readiness false. Do not bypass validation. Re-publish corrected build under new ID.

## Explanation Integrity

Unsupported or contradicted explanation is product-integrity incident. Disable affected build, retain report inputs, and run evidence/contribution audit before republishing.

## Recovery Evidence

Record detection time, affected Build ID, request error counts, mitigation, rollback verification, root cause, and corrective test. Exclude free-text intent and personal data.
