# NextSteamGame v2

NextSteamGame v2 is a greenfield product for finding games that share qualities a player values, beyond storefront genres and broad audience similarity.

> Describe what matters about a game. Get recommendations with inspectable reasons.

## Status

Foundation and independent product specification are in progress. No production application or data artifact exists yet.

## Product Shape

Initial release will let a player:

1. Find one Steam game.
2. Choose valued mechanics, narrative, vibe, and structure or gameplay-loop qualities.
3. Include or exclude identity concepts and niche anchors.
4. Receive ranked recommendations.
5. Inspect deterministic score contributions and source-backed reasons.
6. Refine intent and rerank results.

See [product brief](docs/product/product-brief.md), [user journeys](docs/product/user-journeys.md), and [evaluation protocol](evaluation/relevance/protocol.md).

## Architecture

- Next.js owns browser presentation.
- Rust owns online search, retrieval, scoring, and explanations.
- Python owns acquisition, analysis, machine learning, and immutable artifact publication.
- Normal recommendation requests perform no model inference.
- Published builds are immutable and validated before service readiness.

See [architecture overview](docs/architecture/overview.md) and [decision records](docs/decisions/README.md).

## Clean-Room Boundary

V2 has parentless Git history and no implementation dependency on the previous product. Legacy behavior may inform newly written requirements or tests, but legacy code, schemas, assets, prompts, data, generated artifacts, and configuration cannot enter this tree or any v2 build.

Read [CONTRIBUTING.md](CONTRIBUTING.md) before contributing.
