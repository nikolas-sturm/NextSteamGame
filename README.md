# NextSteamGame v2

NextSteamGame v2 is a greenfield product for finding games that share qualities a player values, beyond storefront genres and broad audience similarity.

> Describe what matters about a game. Get recommendations with inspectable reasons.

## Status

Runnable vertical slice exists for all three product layers:

- Python 3.13 pipeline acquires resumable upstream shards and publishes immutable graph and Zvec builds.
- Rust API validates builds and serves deterministic graph retrieval with dynamic-vector fallback.
- Next.js web product supports search, weighted intent, explanations, refinement, and sharing.

Exact 500- and 2,000-game upstream stages, artifact audits, candidate recall, and local concurrent API baselines are measured in [evaluation reports](evaluation/reports/README.md). Synthetic artifacts remain test-only, and production rejects them unless explicitly enabled. Human relevance studies, GPU model selection, 5,000/full-catalog stages, alpha evidence, and production launch remain measured external gates, not assumed achievements.

See [roadmap status](docs/roadmap-status.md).

## Product Shape

Initial release lets a player:

1. Find one Steam game.
2. Choose valued mechanics, narrative, vibe, and structure or gameplay-loop qualities.
3. Include or exclude identity concepts and niche anchors.
4. Receive ranked recommendations.
5. Inspect deterministic score contributions and source-backed reasons.
6. Refine intent, rerank, and share stable intent.

See [product brief](docs/product/product-brief.md), [user journeys](docs/product/user-journeys.md), and [evaluation protocol](evaluation/relevance/protocol.md).

## Quick Start

Prerequisites: Rust 1.89, uv, Python 3.13 through uv, Node.js 24, and npm.

```powershell
uv sync --frozen --all-groups
uv run nextsteam-pipeline publish-test-fixture --output builds/fixtures
& "tools\smoke.ps1" -ArtifactDir "builds\fixtures\releases\synthetic-fixture-v1"

cd apps/web
npm ci
npm run dev
```

Web uses exact generated OpenAPI transport types. With no `API_BASE_URL`, local UI serves explicit synthetic mock data. Set `API_BASE_URL=http://127.0.0.1:8080` to use Rust service.

## Checks

```text
cargo fmt --all --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
uv run ruff format --check pipeline
uv run ruff check pipeline
uv run mypy
uv run pytest
npm run generate:api
npm run lint
npm run typecheck
npm test
npm run build
npm run e2e
```

Run npm commands from `apps/web`.

## Architecture

- Next.js owns browser presentation.
- Rust owns online search, retrieval, scoring, and explanations.
- Python owns acquisition, analysis, machine learning, and immutable artifact publication.
- Normal recommendation requests perform no model inference.
- Published builds are immutable and validated before service readiness.

See [architecture overview](docs/architecture/overview.md), [OpenAPI](schemas/api/openapi.yaml), and [decision records](docs/decisions/README.md).

## Clean-Room Boundary

V2 has parentless Git history and no implementation dependency on previous product. Legacy behavior may inform newly written requirements or tests, but legacy code, schemas, assets, prompts, data, generated artifacts, and configuration cannot enter this tree or any v2 build.

Read [CONTRIBUTING.md](CONTRIBUTING.md) before contributing.
