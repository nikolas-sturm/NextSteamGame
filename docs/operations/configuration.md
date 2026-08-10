# Configuration And Secrets

## Runtime Configuration

| Variable | Owner | Purpose |
| --- | --- | --- |
| `ARTIFACT_DIR` | API | Read-only path to one validated build. |
| `API_BIND` | API | Listener address, default `0.0.0.0:8080`. |
| `CORS_ORIGINS` | API | Comma-separated exact browser origins. Empty denies cross-origin browser requests. |
| `RUST_LOG` | API | Structured tracing filter. |
| `API_BASE_URL` | Web | Server-side API origin. Never exposed as secret. |
| `NEXT_TELEMETRY_DISABLED` | Web | Disables framework telemetry in controlled builds. |

## Secret Policy

No secret belongs in Git, immutable data builds, browser bundles, image layers, logs, or evaluation reports. Local values use ignored `.env` files. CI and deployment consume scoped secret stores. Rotate exposed credentials immediately; do not preserve compatibility with compromised values.

Steam public Store and review endpoints do not require a project secret. Any future key-bearing source receives a separate least-privilege credential and source-specific rate-limit policy.

## Environments

Development may use synthetic fixture artifacts. CI uses newly authored synthetic data only. Staging and production use independently published upstream-derived builds mounted read-only. Production rejects fixture mode.
