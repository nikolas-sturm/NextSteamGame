# Deployment And Rollback

Target is long-running Linux container host. Build and service releases remain independent but are activated as compatible pair.

## Deploy

1. Publish complete build under versioned path and verify manifest checksums offline.
2. Start API candidate with exact read-only build mount.
3. Require `/healthz` and `/readyz` success; verify reported Build ID.
4. Run deterministic smoke query and compare expected result digest.
5. Start web candidate against API candidate.
6. Shift proxy traffic gradually while monitoring typed errors, latency, memory, and degradation.
7. Retain previous service image and artifact mount.

## Rollback

1. Stop traffic shift.
2. Restore previous web and API image references.
3. Restore previous compatible artifact mount in same deployment operation.
4. Verify readiness Build ID and deterministic smoke digest.
5. Record incident without mutating failed build.

Never repair published artifacts in place. Replacement publication receives new Build ID.
