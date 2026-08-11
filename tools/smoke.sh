#!/usr/bin/env bash
set -euo pipefail

artifact_dir="${1:?artifact directory is required}"
port="${2:-18080}"
ready_timeout_seconds="${3:-120}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
build_id="$(jq -r '.build_id' "$artifact_dir/manifest.json")"
search_name="$(jq -r '.games[0].name' "$artifact_dir/metadata.json")"
search_appid="$(jq -r '.games[0].appid' "$artifact_dir/metadata.json")"
seed_appid="$(jq -r 'first(.records[] | select(.candidates | length > 0) | .source_appid)' "$artifact_dir/graph.json")"
candidate_count="$(jq -r 'first(.records[] | select(.candidates | length > 0) | .candidates | length)' "$artifact_dir/graph.json")"
expected_top_appid="$(jq -r 'first(.records[] | select(.candidates | length > 0)) | .candidates | sort_by([-(.lane_similarities.mechanics + .lane_similarities.narrative + .lane_similarities.vibe + .lane_similarities.structure_loop), .appid]) | first | .appid' "$artifact_dir/graph.json")"
fixture_kind="$(jq -r '.acquisition_windows.kind // ""' "$artifact_dir/manifest.json")"
expected_mode="candidate_graph"
if [[ -f "$artifact_dir/vectors/config.json" && "$candidate_count" -lt 50 ]]; then
  expected_mode="dynamic_vector"
fi
if [[ -z "$build_id" || "$build_id" == "null" || -z "$search_name" || "$search_name" == "null" || "$seed_appid" == "null" || "$expected_top_appid" == "null" ]]; then
  echo "artifact needs at least one game and one candidate edge" >&2
  exit 1
fi

cd "$repo_root"
cargo build --locked -p api
environment=("ARTIFACT_DIR=$artifact_dir" "API_BIND=127.0.0.1:$port" "RUST_LOG=warn")
if [[ "$fixture_kind" == "test_fixture" ]]; then
  environment+=("ALLOW_FIXTURE_ARTIFACTS=1")
fi
env "${environment[@]}" target/debug/api >"${TMPDIR:-/tmp}/nextsteam-api-smoke.log" 2>&1 &
api_pid=$!
trap 'kill "$api_pid" 2>/dev/null || true' EXIT

for _ in $(seq 1 $((ready_timeout_seconds * 4))); do
  if curl --fail --silent "http://127.0.0.1:$port/readyz" >/dev/null; then
    break
  fi
  sleep 0.25
done

curl --fail --silent "http://127.0.0.1:$port/healthz" \
  | jq --arg build_id "$build_id" --exit-status '.status == "ok" and .build_id == $build_id' >/dev/null
curl --fail --silent --get "http://127.0.0.1:$port/v1/games/search" --data-urlencode "q=$search_name" \
  | jq --argjson appid "$search_appid" --exit-status '.games | map(.appid) | index($appid) != null' >/dev/null
request="$(jq -cn --argjson appid "$seed_appid" '{seeds:[{appid:$appid,weight:1.0}],intent:{lane_weights:{mechanics:1.0,narrative:1.0,vibe:1.0,structure_loop:1.0},include:[],exclude:[],text:null},limit:10}')"
curl --fail --silent --request POST "http://127.0.0.1:$port/v1/recommendations" \
  --header "content-type: application/json" \
  --data "$request" \
  | jq --arg build_id "$build_id" --arg mode "$expected_mode" --argjson appid "$expected_top_appid" --argjson seed "$seed_appid" --exit-status '.build_id == $build_id and .retrieval.mode == $mode and (if $mode == "candidate_graph" then .results[0].game.appid == $appid else (.results | length > 0) and .results[0].game.appid != $seed end)' >/dev/null
