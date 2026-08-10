#!/usr/bin/env bash
set -euo pipefail

artifact_dir="${1:?artifact directory is required}"
port="${2:-18080}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$repo_root"
cargo build --locked -p api
ARTIFACT_DIR="$artifact_dir" ALLOW_FIXTURE_ARTIFACTS=1 \
  API_BIND="127.0.0.1:$port" RUST_LOG=warn \
  target/debug/api >"${TMPDIR:-/tmp}/nextsteam-api-smoke.log" 2>&1 &
api_pid=$!
trap 'kill "$api_pid" 2>/dev/null || true' EXIT

for _ in $(seq 1 40); do
  if curl --fail --silent "http://127.0.0.1:$port/readyz" >/dev/null; then
    break
  fi
  sleep 0.25
done

curl --fail --silent "http://127.0.0.1:$port/healthz" \
  | jq --exit-status '.status == "ok" and .build_id == "synthetic-fixture-v1"' >/dev/null
curl --fail --silent "http://127.0.0.1:$port/v1/games/search?q=Fixture" \
  | jq --exit-status '.games | length == 2' >/dev/null
curl --fail --silent --request POST "http://127.0.0.1:$port/v1/recommendations" \
  --header "content-type: application/json" \
  --data '{"seeds":[{"appid":900001,"weight":1.0}],"intent":{"lane_weights":{"mechanics":1.0,"narrative":1.0,"vibe":1.0,"structure_loop":1.0},"include":[],"exclude":[],"text":null},"limit":10}' \
  | jq --exit-status '.build_id == "synthetic-fixture-v1" and .results[0].game.appid == 900002' >/dev/null
