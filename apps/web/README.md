# NextSteamGame Web

Next.js App Router presentation for v2 recommendation journey. Browser code owns interaction and view state; Rust API owns retrieval, scoring, and explanations.

## Development

```bash
npm ci
npm run generate:api
npm run dev
```

Open `http://localhost:3000`. Without `API_BASE_URL`, route handlers use clearly synthetic local data. Set `API_BASE_URL=http://127.0.0.1:8080` before starting server to proxy exact v1 API routes.

## Contracts

`../../schemas/api/openapi.yaml` is transport source. `src/transport/generated.ts` is generated and must not be edited manually. UI models under `src/models` remain independent from transport shapes.

## Checks

```bash
npm run generate:api
npm run lint
npm run typecheck
npm test
npm run build
npm run e2e
```

Production build uses standalone output for long-running Linux container deployment.
