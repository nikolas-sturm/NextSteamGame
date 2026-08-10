use std::{collections::BTreeMap, sync::Arc, time::Duration};

use artifact_store::ArtifactStore;
use axum::{
    Json, Router,
    body::Body,
    extract::{
        DefaultBodyLimit, Extension, Path, Query, Request, State,
        rejection::{JsonRejection, PathRejection, QueryRejection},
    },
    http::{HeaderValue, StatusCode},
    middleware::{self, Next},
    response::{IntoResponse, Response},
    routing::{get, post},
};
use domain::{
    ApiErrorBody, ApiErrorDetail, BuildId, Evidence, Game, GameId, Lane, Recommendation,
    RecommendationRequest, RecommendationResponse, ScoreContribution,
};
use retrieval::{CandidateRetriever, ImmutableGraph};
use serde::{Deserialize, Serialize};
use tower_http::{
    cors::{AllowOrigin, CorsLayer},
    request_id::{MakeRequestUuid, PropagateRequestIdLayer, RequestId, SetRequestIdLayer},
    trace::TraceLayer,
};

pub const MAX_RESULTS: usize = 100;
const MAX_SEARCH_RESULTS: usize = 50;
const MAX_BODY_BYTES: usize = 64 * 1024;
const REQUEST_TIMEOUT: Duration = Duration::from_secs(10);

#[derive(Clone)]
pub struct AppState {
    build_id: BuildId,
    metadata: Arc<BTreeMap<GameId, Game>>,
    evidence: Arc<BTreeMap<String, Evidence>>,
    retriever: Arc<dyn CandidateRetriever>,
}

impl AppState {
    pub fn from_artifacts(store: ArtifactStore) -> Self {
        Self {
            build_id: store.manifest.build_id,
            metadata: Arc::new(store.metadata),
            evidence: Arc::new(store.evidence),
            retriever: Arc::new(store.graph),
        }
    }

    pub fn fixture(
        build_id: BuildId,
        metadata: BTreeMap<GameId, Game>,
        evidence: BTreeMap<String, Evidence>,
        graph: ImmutableGraph,
    ) -> Self {
        Self {
            build_id,
            metadata: Arc::new(metadata),
            evidence: Arc::new(evidence),
            retriever: Arc::new(graph),
        }
    }
}

pub fn router(state: AppState, cors_origins: &[String]) -> Result<Router, String> {
    let cors = if cors_origins.is_empty() {
        CorsLayer::new()
    } else {
        let origins = cors_origins
            .iter()
            .map(|origin| {
                origin
                    .parse::<HeaderValue>()
                    .map_err(|error| format!("invalid CORS origin {origin}: {error}"))
            })
            .collect::<Result<Vec<_>, _>>()?;
        CorsLayer::new().allow_origin(AllowOrigin::list(origins))
    };
    Ok(Router::new()
        .route("/healthz", get(health))
        .route("/readyz", get(ready))
        .route("/v1/config", get(config))
        .route("/v1/games/search", get(search_games))
        .route("/v1/games/{appid}", get(game))
        .route("/v1/recommendations", post(recommend))
        .fallback(not_found)
        .with_state(state)
        .layer(DefaultBodyLimit::max(MAX_BODY_BYTES))
        .layer(middleware::from_fn(request_timeout))
        .layer(PropagateRequestIdLayer::x_request_id())
        .layer(SetRequestIdLayer::new(
            http::HeaderName::from_static("x-request-id"),
            MakeRequestUuid,
        ))
        .layer(cors)
        .layer(TraceLayer::new_for_http()))
}

#[derive(Serialize)]
struct HealthResponse {
    status: &'static str,
    build_id: BuildId,
}
async fn health(State(state): State<AppState>) -> Json<HealthResponse> {
    Json(HealthResponse {
        status: "ok",
        build_id: state.build_id,
    })
}

#[derive(Serialize)]
struct ReadyResponse {
    status: &'static str,
    build_id: BuildId,
}
async fn ready(State(state): State<AppState>) -> Json<ReadyResponse> {
    Json(ReadyResponse {
        status: "ready",
        build_id: state.build_id,
    })
}

#[derive(Serialize)]
struct ConfigResponse {
    build_id: BuildId,
    max_results: usize,
    max_body_bytes: usize,
    lanes: [Lane; 4],
}
async fn config(State(state): State<AppState>) -> Json<ConfigResponse> {
    Json(ConfigResponse {
        build_id: state.build_id,
        max_results: MAX_RESULTS,
        max_body_bytes: MAX_BODY_BYTES,
        lanes: [
            Lane::Mechanics,
            Lane::Narrative,
            Lane::Vibe,
            Lane::StructureLoop,
        ],
    })
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct SearchQuery {
    q: String,
    #[serde(default = "default_search_limit")]
    limit: usize,
}
const fn default_search_limit() -> usize {
    20
}
#[derive(Serialize, Deserialize)]
struct GameSearchResponse {
    games: Vec<Game>,
}

async fn search_games(
    State(state): State<AppState>,
    Extension(request_id): Extension<RequestId>,
    query: Result<Query<SearchQuery>, QueryRejection>,
) -> Result<Json<GameSearchResponse>, ApiError> {
    let Query(query) = query
        .map_err(|error| ApiError::bad_request("invalid_query", &error.body_text(), &request_id))?;
    let term = query.q.trim().to_lowercase();
    if !(2..=100).contains(&term.chars().count())
        || !(1..=MAX_SEARCH_RESULTS).contains(&query.limit)
    {
        return Err(ApiError::bad_request(
            "invalid_search",
            "q length must be 2..=100 and limit must be 1..=50",
            &request_id,
        ));
    }
    let mut games: Vec<_> = state
        .metadata
        .values()
        .filter(|game| game.name.to_lowercase().contains(&term))
        .cloned()
        .collect();
    games.sort_by(|left, right| {
        left.name
            .to_lowercase()
            .cmp(&right.name.to_lowercase())
            .then_with(|| left.appid.cmp(&right.appid))
    });
    games.truncate(query.limit);
    Ok(Json(GameSearchResponse { games }))
}

async fn game(
    State(state): State<AppState>,
    Extension(request_id): Extension<RequestId>,
    appid: Result<Path<u32>, PathRejection>,
) -> Result<Json<Game>, ApiError> {
    let Path(appid) = appid
        .map_err(|error| ApiError::bad_request("invalid_appid", &error.body_text(), &request_id))?;
    if appid == 0 {
        return Err(ApiError::bad_request(
            "invalid_appid",
            "appid must be positive",
            &request_id,
        ));
    }
    state
        .metadata
        .get(&GameId(appid))
        .cloned()
        .map(Json)
        .ok_or_else(|| ApiError::not_found("game_not_found", "game not found", &request_id))
}

async fn recommend(
    State(state): State<AppState>,
    Extension(request_id): Extension<RequestId>,
    payload: Result<Json<RecommendationRequest>, JsonRejection>,
) -> Result<Json<RecommendationResponse>, ApiError> {
    let Json(request) = payload.map_err(|error| {
        ApiError::new(
            error.status(),
            "invalid_json",
            &error.body_text(),
            Some(&request_id),
        )
    })?;
    validate_request(&request)
        .map_err(|message| ApiError::bad_request("invalid_request", message, &request_id))?;
    if request
        .intent
        .text
        .as_ref()
        .is_some_and(|text| !text.trim().is_empty())
    {
        return Err(ApiError::bad_request(
            "unsupported_free_text",
            "free-text intent requires dynamic retrieval and is not supported",
            &request_id,
        ));
    }
    let normalized_intent = recommendation_core::normalize(&request.seeds, &request.intent)
        .map_err(|error| {
            ApiError::bad_request("invalid_intent", &error.to_string(), &request_id)
        })?;
    let retrieval = state
        .retriever
        .retrieve(&normalized_intent, MAX_RESULTS * 10);
    let ranked = recommendation_core::rank(&normalized_intent, retrieval.candidates, request.limit)
        .map_err(|error| {
            ApiError::bad_request("invalid_intent", &error.to_string(), &request_id)
        })?;
    let results = ranked
        .into_iter()
        .enumerate()
        .filter_map(|(index, ranked)| {
            let game = state.metadata.get(&ranked.game_id)?.clone();
            let evidence = hydrate_evidence(&ranked.contributions, &state.evidence);
            let explanation = explanation(&ranked.contributions);
            Some(Recommendation {
                rank: index + 1,
                game,
                score: ranked.score,
                contributions: ranked.contributions,
                matched_concepts: ranked.matched_concepts,
                explanation,
                evidence,
            })
        })
        .collect();
    Ok(Json(RecommendationResponse {
        build_id: state.build_id,
        normalized_intent,
        retrieval: retrieval.state,
        results,
    }))
}

fn validate_request(request: &RecommendationRequest) -> Result<(), &'static str> {
    if !(1..=8).contains(&request.seeds.len()) || !(1..=MAX_RESULTS).contains(&request.limit) {
        return Err("seeds must contain 1..=8 items and limit must be 1..=100");
    }
    if request.seeds.iter().any(|seed| seed.appid.0 == 0) {
        return Err("seed appid must be positive");
    }
    if request.intent.include.len() > 20 || request.intent.exclude.len() > 20 {
        return Err("include and exclude support at most 20 items");
    }
    if request
        .intent
        .include
        .iter()
        .chain(&request.intent.exclude)
        .any(|value| value.trim().is_empty() || value.chars().count() > 80)
    {
        return Err("concept strings must contain 1..=80 characters");
    }
    if request
        .intent
        .text
        .as_ref()
        .is_some_and(|value| value.chars().count() > 500)
    {
        return Err("text supports at most 500 characters");
    }
    Ok(())
}

fn hydrate_evidence(
    contributions: &[ScoreContribution],
    evidence: &BTreeMap<String, Evidence>,
) -> Vec<Evidence> {
    let mut ids: Vec<_> = contributions
        .iter()
        .flat_map(|item| &item.evidence_ids)
        .collect();
    ids.sort();
    ids.dedup();
    ids.into_iter()
        .filter_map(|id| evidence.get(id).cloned())
        .collect()
}

fn explanation(contributions: &[ScoreContribution]) -> String {
    let mut strongest: Vec<_> = contributions
        .iter()
        .filter(|item| item.value > 0.0)
        .collect();
    strongest.sort_by(|left, right| {
        right
            .value
            .total_cmp(&left.value)
            .then_with(|| left.key.cmp(&right.key))
    });
    let labels: Vec<_> = strongest
        .into_iter()
        .take(2)
        .map(|item| item.label.as_str())
        .collect();
    if labels.is_empty() {
        "No positive scoring signals available.".into()
    } else {
        format!("Strongest matches: {}.", labels.join(" and "))
    }
}

async fn not_found(Extension(request_id): Extension<RequestId>) -> ApiError {
    ApiError::not_found("route_not_found", "route not found", &request_id)
}
async fn request_timeout(request: Request<Body>, next: Next) -> Response {
    let request_id = request.extensions().get::<RequestId>().cloned();
    match tokio::time::timeout(REQUEST_TIMEOUT, next.run(request)).await {
        Ok(response) => response,
        Err(_) => ApiError::new(
            StatusCode::REQUEST_TIMEOUT,
            "request_timeout",
            "request timed out",
            request_id.as_ref(),
        )
        .into_response(),
    }
}

pub struct ApiError {
    status: StatusCode,
    body: ApiErrorBody,
}
impl ApiError {
    fn new(status: StatusCode, code: &str, message: &str, request_id: Option<&RequestId>) -> Self {
        Self {
            status,
            body: ApiErrorBody {
                error: ApiErrorDetail {
                    code: code.into(),
                    message: message.into(),
                },
                request_id: request_id
                    .and_then(|id| id.header_value().to_str().ok())
                    .unwrap_or("unknown")
                    .into(),
            },
        }
    }
    fn bad_request(code: &str, message: &str, request_id: &RequestId) -> Self {
        Self::new(StatusCode::BAD_REQUEST, code, message, Some(request_id))
    }
    fn not_found(code: &str, message: &str, request_id: &RequestId) -> Self {
        Self::new(StatusCode::NOT_FOUND, code, message, Some(request_id))
    }
}
impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        (self.status, Json(self.body)).into_response()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::to_bytes;
    use domain::{LaneWeights, RetrievalMode};
    use retrieval::{GraphCandidate, GraphEnvelope, GraphRecord};
    use tower::ServiceExt;

    fn app() -> Router {
        let graph = ImmutableGraph::from_envelope(GraphEnvelope {
            build_id: BuildId("fixture-1".into()),
            lanes: vec![
                Lane::Mechanics,
                Lane::Narrative,
                Lane::Vibe,
                Lane::StructureLoop,
            ],
            records: vec![GraphRecord {
                source_appid: GameId(1),
                candidates: vec![GraphCandidate {
                    appid: GameId(2),
                    lane_similarities: LaneWeights {
                        mechanics: 0.9,
                        narrative: 0.0,
                        vibe: 0.0,
                        structure_loop: 0.0,
                    },
                    matched_concepts: [(Lane::Mechanics, vec!["cozy".into()])].into(),
                    evidence_ids: vec!["e1".into()],
                    features: [("identity".into(), 1.0)].into(),
                }],
            }],
        })
        .unwrap();
        let game = Game {
            appid: GameId(2),
            name: "Clockwork".into(),
            short_description: "Systems game".into(),
            release_year: Some(2024),
            header_image_url: Some("https://example.invalid/header.jpg".into()),
            steam_url: "https://store.steampowered.com/app/2".into(),
        };
        let evidence = Evidence {
            id: "e1".into(),
            appid: GameId(2),
            source: "review".into(),
            excerpt: "Deep mechanical systems".into(),
        };
        router(
            AppState::fixture(
                BuildId("fixture-1".into()),
                [(GameId(2), game)].into(),
                [("e1".into(), evidence)].into(),
                graph,
            ),
            &[],
        )
        .unwrap()
    }

    fn request(text: Option<&str>) -> serde_json::Value {
        serde_json::json!({"seeds":[{"appid":1,"weight":1.0}],"intent":{"lane_weights":{"mechanics":1.0,"narrative":0.0,"vibe":0.0,"structure_loop":0.0},"include":[" Cozy "],"exclude":[],"text":text},"limit":10})
    }

    #[tokio::test]
    async fn openapi_shape_hydrates_explanation_evidence() {
        let response = app()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/v1/recommendations")
                    .header("content-type", "application/json")
                    .body(Body::from(request(None).to_string()))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body: RecommendationResponse =
            serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap())
                .unwrap();
        assert_eq!(body.retrieval.mode, RetrievalMode::CandidateGraph);
        assert_eq!(body.normalized_intent.include, ["cozy"]);
        assert_eq!(body.results[0].rank, 1);
        assert_eq!(body.results[0].evidence[0].id, "e1");
        assert!(body.results[0].explanation.contains("Mechanics fit"));
    }

    #[tokio::test]
    async fn search_wraps_games_and_free_text_is_typed_error() {
        let search = app()
            .oneshot(
                Request::builder()
                    .uri("/v1/games/search?q=clock&limit=5")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        let body: GameSearchResponse =
            serde_json::from_slice(&to_bytes(search.into_body(), usize::MAX).await.unwrap())
                .unwrap();
        assert_eq!(body.games[0].appid, GameId(2));
        let response = app()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/v1/recommendations")
                    .header("content-type", "application/json")
                    .body(Body::from(request(Some("crafting")).to_string()))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let error: ApiErrorBody =
            serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap())
                .unwrap();
        assert_eq!(error.error.code, "unsupported_free_text");
    }

    #[tokio::test]
    async fn malformed_input_has_typed_error() {
        let response = app()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/v1/recommendations")
                    .header("content-type", "application/json")
                    .body(Body::from("{"))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let error: ApiErrorBody =
            serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap())
                .unwrap();
        assert_eq!(error.error.code, "invalid_json");
        assert_ne!(error.request_id, "unknown");
    }

    #[test]
    fn lane_weights_serialize_to_contract_names() {
        let value = serde_json::to_value(LaneWeights {
            mechanics: 1.0,
            narrative: 0.0,
            vibe: 0.0,
            structure_loop: 0.0,
        })
        .unwrap();
        assert!(value.get("structure_loop").is_some());
        assert_eq!(value.as_object().unwrap().len(), 4);
    }
}
