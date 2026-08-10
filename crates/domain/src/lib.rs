use serde::{Deserialize, Serialize};

pub const API_COMPATIBILITY_VERSION: u32 = 1;
pub const ARTIFACT_SCHEMA_VERSION: u32 = 1;

#[derive(Clone, Copy, Debug, Deserialize, Eq, Hash, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(transparent)]
pub struct GameId(pub u32);

#[derive(Clone, Debug, Deserialize, Eq, Hash, PartialEq, Serialize)]
#[serde(transparent)]
pub struct BuildId(pub String);

#[derive(Clone, Copy, Debug, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Lane {
    Mechanics,
    Narrative,
    Vibe,
    StructureLoop,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LaneWeights {
    pub mechanics: f64,
    pub narrative: f64,
    pub vibe: f64,
    pub structure_loop: f64,
}

impl LaneWeights {
    pub fn iter(self) -> [(Lane, f64); 4] {
        [
            (Lane::Mechanics, self.mechanics),
            (Lane::Narrative, self.narrative),
            (Lane::Vibe, self.vibe),
            (Lane::StructureLoop, self.structure_loop),
        ]
    }

    pub fn get(self, lane: Lane) -> f64 {
        match lane {
            Lane::Mechanics => self.mechanics,
            Lane::Narrative => self.narrative,
            Lane::Vibe => self.vibe,
            Lane::StructureLoop => self.structure_loop,
        }
    }
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Seed {
    pub appid: GameId,
    pub weight: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct IntentInput {
    pub lane_weights: LaneWeights,
    pub include: Vec<String>,
    pub exclude: Vec<String>,
    pub text: Option<String>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RecommendationRequest {
    pub seeds: Vec<Seed>,
    pub intent: IntentInput,
    pub limit: usize,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct NormalizedIntent {
    pub seeds: Vec<Seed>,
    pub lane_weights: LaneWeights,
    pub include: Vec<String>,
    pub exclude: Vec<String>,
    pub text: Option<String>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct CandidateFeatures {
    pub game_id: GameId,
    pub lanes: LaneWeights,
    #[serde(default)]
    pub concepts: Vec<String>,
    #[serde(default)]
    pub evidence_ids: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct ScoreContribution {
    pub key: String,
    pub label: String,
    pub lane: Option<Lane>,
    pub value: f64,
    pub evidence_ids: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct RankedCandidate {
    pub game_id: GameId,
    pub score: f64,
    pub contributions: Vec<ScoreContribution>,
    pub matched_concepts: Vec<String>,
    pub missing_lanes: Vec<Lane>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Game {
    pub appid: GameId,
    pub name: String,
    pub short_description: String,
    pub release_year: Option<u16>,
    pub header_image_url: Option<String>,
    pub steam_url: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Evidence {
    pub id: String,
    pub appid: GameId,
    pub source: String,
    pub excerpt: String,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct Recommendation {
    pub rank: usize,
    pub game: Game,
    pub score: f64,
    pub contributions: Vec<ScoreContribution>,
    pub matched_concepts: Vec<String>,
    pub explanation: String,
    pub evidence: Vec<Evidence>,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum RetrievalMode {
    CandidateGraph,
    DynamicVector,
    SparseFallback,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct RetrievalState {
    pub mode: RetrievalMode,
    pub reduced_confidence: bool,
    pub reason: Option<String>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct RecommendationResponse {
    pub build_id: BuildId,
    pub normalized_intent: NormalizedIntent,
    pub retrieval: RetrievalState,
    pub results: Vec<Recommendation>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct ApiErrorBody {
    pub error: ApiErrorDetail,
    pub request_id: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct ApiErrorDetail {
    pub code: String,
    pub message: String,
}
