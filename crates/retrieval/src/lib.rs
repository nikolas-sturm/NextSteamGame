use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    io::Read,
    path::Path,
    sync::{Arc, OnceLock},
};

use domain::{
    BuildId, CandidateFeatures, GameId, Lane, LaneWeights, NormalizedIntent, RetrievalMode,
    RetrievalState,
};
use serde::{Deserialize, Serialize};
use thiserror::Error;
use zvec_rust::{Collection, CollectionOptions, SearchQuery};

pub trait CandidateRetriever: Send + Sync {
    fn retrieve(&self, intent: &NormalizedIntent, limit: usize) -> Retrieval;
}

#[derive(Clone, Debug)]
pub struct Retrieval {
    pub state: RetrievalState,
    pub candidates: Vec<CandidateFeatures>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GraphEnvelope {
    pub build_id: BuildId,
    pub lanes: Vec<Lane>,
    pub records: Vec<GraphRecord>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GraphRecord {
    pub source_appid: GameId,
    pub candidates: Vec<GraphCandidate>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GraphCandidate {
    pub appid: GameId,
    pub lane_similarities: LaneWeights,
    pub matched_concepts: BTreeMap<Lane, Vec<String>>,
    pub evidence_ids: Vec<String>,
    pub features: BTreeMap<String, f64>,
}

#[derive(Clone, Debug)]
pub struct ImmutableGraph {
    build_id: BuildId,
    edges: Arc<BTreeMap<GameId, Vec<CandidateFeatures>>>,
    edge_count: usize,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct VectorConfig {
    build_id: BuildId,
    #[serde(rename = "model")]
    _model: serde_json::Value,
    lanes: BTreeMap<Lane, VectorLaneConfig>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct VectorLaneConfig {
    count: usize,
    dimensions: usize,
    index_kind: String,
    dtype: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct VectorMetadata {
    appid: u32,
    #[serde(default)]
    concepts: Vec<String>,
    #[serde(default)]
    evidence_ids: Vec<String>,
}

pub struct ZvecRetriever {
    build_id: BuildId,
    collections: BTreeMap<Lane, Collection>,
    _working_copy: tempfile::TempDir,
}

fn copy_tree(source: &Path, destination: &Path) -> std::io::Result<()> {
    fs::create_dir_all(destination)?;
    for entry in fs::read_dir(source)? {
        let entry = entry?;
        let file_type = entry.file_type()?;
        let target = destination.join(entry.file_name());
        if file_type.is_dir() {
            copy_tree(&entry.path(), &target)?;
        } else if file_type.is_file() {
            fs::copy(entry.path(), target)?;
        } else {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "vector artifacts cannot contain symlinks",
            ));
        }
    }
    Ok(())
}

impl ZvecRetriever {
    pub fn open(root: impl AsRef<Path>, expected_build_id: &BuildId) -> Result<Self, String> {
        static INITIALIZED: OnceLock<Result<(), String>> = OnceLock::new();
        INITIALIZED
            .get_or_init(|| zvec_rust::initialize(None).map_err(|error| error.to_string()))
            .as_ref()
            .map_err(Clone::clone)?;

        let source_root = root.as_ref();
        let config: VectorConfig = serde_json::from_reader(
            fs::File::open(source_root.join("config.json")).map_err(|error| error.to_string())?,
        )
        .map_err(|error| error.to_string())?;
        let working_copy = tempfile::tempdir().map_err(|error| error.to_string())?;
        copy_tree(source_root, working_copy.path()).map_err(|error| error.to_string())?;
        let root = working_copy.path();
        if &config.build_id != expected_build_id {
            return Err("vector config build_id does not match artifact".into());
        }
        let mut collections = BTreeMap::new();
        for (lane, lane_config) in config.lanes {
            if lane_config.dimensions == 0
                || lane_config.dtype != "fp32"
                || !matches!(lane_config.index_kind.as_str(), "flat" | "hnsw")
            {
                return Err(format!("unsupported {lane:?} vector configuration"));
            }
            let mut options = CollectionOptions::new().map_err(|error| error.to_string())?;
            options
                .set_read_only(true)
                .map_err(|error| error.to_string())?;
            let lane_name = match lane {
                Lane::Mechanics => "mechanics",
                Lane::Narrative => "narrative",
                Lane::Vibe => "vibe",
                Lane::StructureLoop => "structure_loop",
            };
            let path = root.join(lane_name);
            let path = path
                .to_str()
                .ok_or_else(|| "vector path is not UTF-8".to_string())?;
            let collection =
                Collection::open(path, Some(&options)).map_err(|error| error.to_string())?;
            let stats = collection.stats().map_err(|error| error.to_string())?;
            if stats.doc_count != lane_config.count as u64 {
                return Err(format!("{lane:?} vector count does not match config"));
            }
            collections.insert(lane, collection);
        }
        if collections.is_empty() {
            return Err("vector config contains no lane collections".into());
        }
        Ok(Self {
            build_id: config.build_id,
            collections,
            _working_copy: working_copy,
        })
    }

    pub fn build_id(&self) -> &BuildId {
        &self.build_id
    }

    fn retrieve_inner(
        &self,
        intent: &NormalizedIntent,
        limit: usize,
    ) -> Result<Vec<CandidateFeatures>, String> {
        let seed_weights: BTreeMap<_, _> = intent
            .seeds
            .iter()
            .map(|seed| (seed.appid, seed.weight as f32))
            .collect();
        let seed_keys: Vec<_> = intent
            .seeds
            .iter()
            .map(|seed| seed.appid.0.to_string())
            .collect();
        let seed_refs: Vec<_> = seed_keys.iter().map(String::as_str).collect();
        let mut candidates = BTreeMap::new();
        for (lane, lane_weight) in intent.lane_weights.iter() {
            let Some(collection) = self.collections.get(&lane) else {
                continue;
            };
            if lane_weight == 0.0 {
                continue;
            }
            let seeds = collection
                .fetch_with_options(&seed_refs, None, true)
                .map_err(|error| error.to_string())?;
            let mut query_vector = Vec::<f32>::new();
            for seed in seeds {
                let appid = seed
                    .get_pk()
                    .ok_or_else(|| "seed vector has no primary key".to_string())?
                    .parse::<u32>()
                    .map(GameId)
                    .map_err(|error| error.to_string())?;
                let Some(weight) = seed_weights.get(&appid) else {
                    continue;
                };
                let vector = seed
                    .get_vector_f32("embedding")
                    .map_err(|error| error.to_string())?
                    .ok_or_else(|| "seed vector is missing embedding".to_string())?;
                if query_vector.is_empty() {
                    query_vector.resize(vector.len(), 0.0);
                }
                if query_vector.len() != vector.len() {
                    return Err("seed vector dimensions do not match".into());
                }
                for (value, source) in query_vector.iter_mut().zip(vector) {
                    *value += source * weight;
                }
            }
            let norm = query_vector
                .iter()
                .map(|value| value * value)
                .sum::<f32>()
                .sqrt();
            if norm == 0.0 {
                continue;
            }
            for value in &mut query_vector {
                *value /= norm;
            }
            let topk = i32::try_from(limit.max(1)).unwrap_or(i32::MAX);
            let mut query = SearchQuery::new("embedding", &query_vector, topk)
                .map_err(|error| error.to_string())?;
            query
                .set_output_fields(&["metadata_json"])
                .map_err(|error| error.to_string())?;
            for result in collection
                .query(&query)
                .map_err(|error| error.to_string())?
            {
                let metadata: VectorMetadata = serde_json::from_str(
                    &result
                        .get_string("metadata_json")
                        .map_err(|error| error.to_string())?
                        .ok_or_else(|| "vector result is missing metadata".to_string())?,
                )
                .map_err(|error| error.to_string())?;
                if result.get_pk() != Some(metadata.appid.to_string().as_str()) {
                    return Err("vector result primary key does not match metadata".into());
                }
                let entry =
                    candidates
                        .entry(GameId(metadata.appid))
                        .or_insert_with(|| CandidateFeatures {
                            game_id: GameId(metadata.appid),
                            lanes: LaneWeights {
                                mechanics: 0.0,
                                narrative: 0.0,
                                vibe: 0.0,
                                structure_loop: 0.0,
                            },
                            concepts: Vec::new(),
                            evidence_ids: Vec::new(),
                        });
                let score = f64::from(result.get_score()).clamp(0.0, 1.0);
                match lane {
                    Lane::Mechanics => entry.lanes.mechanics = score,
                    Lane::Narrative => entry.lanes.narrative = score,
                    Lane::Vibe => entry.lanes.vibe = score,
                    Lane::StructureLoop => entry.lanes.structure_loop = score,
                }
                entry.concepts.extend(metadata.concepts);
                entry.evidence_ids.extend(metadata.evidence_ids);
            }
        }
        let mut candidates: Vec<_> = candidates.into_values().collect();
        for candidate in &mut candidates {
            candidate.concepts.sort();
            candidate.concepts.dedup();
            candidate.evidence_ids.sort();
            candidate.evidence_ids.dedup();
        }
        Ok(candidates)
    }
}

impl CandidateRetriever for ZvecRetriever {
    fn retrieve(&self, intent: &NormalizedIntent, limit: usize) -> Retrieval {
        match self.retrieve_inner(intent, limit) {
            Ok(candidates) if !candidates.is_empty() => Retrieval {
                state: RetrievalState {
                    mode: RetrievalMode::DynamicVector,
                    reduced_confidence: false,
                    reason: None,
                },
                candidates,
            },
            Ok(_) => Retrieval {
                state: RetrievalState {
                    mode: RetrievalMode::SparseFallback,
                    reduced_confidence: true,
                    reason: Some("no vector coverage for supplied seeds".into()),
                },
                candidates: Vec::new(),
            },
            Err(error) => Retrieval {
                state: RetrievalState {
                    mode: RetrievalMode::SparseFallback,
                    reduced_confidence: true,
                    reason: Some(format!("dynamic vector retrieval failed: {error}")),
                },
                candidates: Vec::new(),
            },
        }
    }
}

pub struct FallbackRetriever {
    primary: Arc<dyn CandidateRetriever>,
    fallback: Arc<dyn CandidateRetriever>,
    minimum_candidates: usize,
}

impl FallbackRetriever {
    pub fn new(
        primary: Arc<dyn CandidateRetriever>,
        fallback: Arc<dyn CandidateRetriever>,
        minimum_candidates: usize,
    ) -> Self {
        Self {
            primary,
            fallback,
            minimum_candidates,
        }
    }
}

impl CandidateRetriever for FallbackRetriever {
    fn retrieve(&self, intent: &NormalizedIntent, limit: usize) -> Retrieval {
        let mut primary = self.primary.retrieve(intent, limit);
        if primary.candidates.len() >= self.minimum_candidates {
            return primary;
        }
        let mut fallback = self.fallback.retrieve(intent, limit);
        if fallback.candidates.is_empty() {
            primary.state.reduced_confidence = true;
            primary.state.reason = fallback.state.reason;
            return primary;
        }
        fallback.state.reason = Some(format!(
            "candidate graph returned {} candidates below configured minimum {}",
            primary.candidates.len(),
            self.minimum_candidates
        ));
        fallback
    }
}

#[derive(Debug, Error, PartialEq)]
pub enum GraphError {
    #[error("candidate graph is invalid JSON: {0}")]
    InvalidJson(String),
    #[error("graph lanes must contain each supported lane exactly once")]
    InvalidLanes,
    #[error("duplicate graph source {0:?}")]
    DuplicateSource(GameId),
    #[error("duplicate candidate {candidate:?} for source {source_appid:?}")]
    DuplicateCandidate {
        source_appid: GameId,
        candidate: GameId,
    },
    #[error("graph contains self-edge for {0:?}")]
    SelfEdge(GameId),
    #[error("graph value {0} is not finite or is negative")]
    InvalidValue(String),
}

impl ImmutableGraph {
    pub fn from_reader(reader: impl Read) -> Result<Self, GraphError> {
        let envelope = serde_json::from_reader(reader)
            .map_err(|error| GraphError::InvalidJson(error.to_string()))?;
        Self::from_envelope(envelope)
    }

    pub fn from_envelope(envelope: GraphEnvelope) -> Result<Self, GraphError> {
        let expected: BTreeSet<_> = [
            Lane::Mechanics,
            Lane::Narrative,
            Lane::Vibe,
            Lane::StructureLoop,
        ]
        .into();
        if envelope.lanes.len() != expected.len()
            || envelope.lanes.iter().copied().collect::<BTreeSet<_>>() != expected
        {
            return Err(GraphError::InvalidLanes);
        }
        let mut edges = BTreeMap::new();
        let mut edge_count = 0;
        for record in envelope.records {
            if edges.contains_key(&record.source_appid) {
                return Err(GraphError::DuplicateSource(record.source_appid));
            }
            let mut seen = BTreeSet::new();
            let mut candidates = Vec::with_capacity(record.candidates.len());
            for candidate in record.candidates {
                if candidate.appid == record.source_appid {
                    return Err(GraphError::SelfEdge(record.source_appid));
                }
                if !seen.insert(candidate.appid) {
                    return Err(GraphError::DuplicateCandidate {
                        source_appid: record.source_appid,
                        candidate: candidate.appid,
                    });
                }
                if let Some((lane, _)) = candidate
                    .lane_similarities
                    .iter()
                    .iter()
                    .find(|(_, value)| !value.is_finite() || *value < 0.0)
                {
                    return Err(GraphError::InvalidValue(
                        format!("lane:{lane:?}").to_lowercase(),
                    ));
                }
                if let Some((key, _)) = candidate
                    .features
                    .iter()
                    .find(|(_, value)| !value.is_finite() || **value < 0.0)
                {
                    return Err(GraphError::InvalidValue(format!("feature:{key}")));
                }
                let mut concepts: Vec<_> =
                    candidate.matched_concepts.into_values().flatten().collect();
                concepts.sort();
                concepts.dedup();
                let mut evidence_ids = candidate.evidence_ids;
                evidence_ids.sort();
                evidence_ids.dedup();
                candidates.push(CandidateFeatures {
                    game_id: candidate.appid,
                    lanes: candidate.lane_similarities,
                    concepts,
                    evidence_ids,
                });
                edge_count += 1;
            }
            candidates.sort_by_key(|candidate| candidate.game_id);
            edges.insert(record.source_appid, candidates);
        }
        Ok(Self {
            build_id: envelope.build_id,
            edges: Arc::new(edges),
            edge_count,
        })
    }

    pub fn build_id(&self) -> &BuildId {
        &self.build_id
    }
    pub fn edge_count(&self) -> usize {
        self.edge_count
    }
    pub fn game_ids(&self) -> impl Iterator<Item = GameId> + '_ {
        self.edges.keys().copied().chain(
            self.edges
                .values()
                .flatten()
                .map(|candidate| candidate.game_id),
        )
    }
    pub fn evidence_ids(&self) -> impl Iterator<Item = &str> + '_ {
        self.edges
            .values()
            .flatten()
            .flat_map(|candidate| candidate.evidence_ids.iter().map(String::as_str))
    }
}

impl CandidateRetriever for ImmutableGraph {
    fn retrieve(&self, intent: &NormalizedIntent, _limit: usize) -> Retrieval {
        let mut candidates = BTreeMap::new();
        for seed in &intent.seeds {
            if let Some(neighbors) = self.edges.get(&seed.appid) {
                for neighbor in neighbors {
                    let entry =
                        candidates
                            .entry(neighbor.game_id)
                            .or_insert_with(|| CandidateFeatures {
                                game_id: neighbor.game_id,
                                lanes: LaneWeights {
                                    mechanics: 0.0,
                                    narrative: 0.0,
                                    vibe: 0.0,
                                    structure_loop: 0.0,
                                },
                                concepts: Vec::new(),
                                evidence_ids: Vec::new(),
                            });
                    entry.lanes.mechanics += neighbor.lanes.mechanics * seed.weight;
                    entry.lanes.narrative += neighbor.lanes.narrative * seed.weight;
                    entry.lanes.vibe += neighbor.lanes.vibe * seed.weight;
                    entry.lanes.structure_loop += neighbor.lanes.structure_loop * seed.weight;
                    entry.concepts.extend(neighbor.concepts.clone());
                    entry.evidence_ids.extend(neighbor.evidence_ids.clone());
                }
            }
        }
        let mut candidates: Vec<_> = candidates.into_values().collect();
        for candidate in &mut candidates {
            candidate.concepts.sort();
            candidate.concepts.dedup();
            candidate.evidence_ids.sort();
            candidate.evidence_ids.dedup();
        }
        // Scorer owns relevance ordering; truncating this GameId-ordered map would drop valid matches.
        let sparse = candidates.is_empty();
        Retrieval {
            state: RetrievalState {
                mode: if sparse {
                    RetrievalMode::SparseFallback
                } else {
                    RetrievalMode::CandidateGraph
                },
                reduced_confidence: sparse,
                reason: sparse.then(|| "no candidate graph edges for supplied seeds".into()),
            },
            candidates,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use domain::Seed;

    fn candidate(appid: u32) -> GraphCandidate {
        GraphCandidate {
            appid: GameId(appid),
            lane_similarities: LaneWeights {
                mechanics: 0.5,
                narrative: 0.25,
                vibe: 0.0,
                structure_loop: 0.0,
            },
            matched_concepts: [
                (Lane::Mechanics, vec!["crafting".into()]),
                (Lane::Vibe, vec!["cozy".into()]),
            ]
            .into(),
            evidence_ids: vec!["e1".into()],
            features: [("identity".into(), 1.0)].into(),
        }
    }
    fn envelope(records: Vec<GraphRecord>) -> GraphEnvelope {
        GraphEnvelope {
            build_id: BuildId("build-1".into()),
            lanes: vec![
                Lane::Mechanics,
                Lane::Narrative,
                Lane::Vibe,
                Lane::StructureLoop,
            ],
            records,
        }
    }

    #[test]
    fn exact_envelope_preserves_lanes_flattens_concepts_and_deduplicates_multi_seed() {
        let graph = ImmutableGraph::from_envelope(envelope(vec![
            GraphRecord {
                source_appid: GameId(1),
                candidates: vec![candidate(3)],
            },
            GraphRecord {
                source_appid: GameId(2),
                candidates: vec![candidate(3)],
            },
        ]))
        .unwrap();
        assert_eq!(graph.edge_count(), 2);
        let intent = NormalizedIntent {
            seeds: vec![
                Seed {
                    appid: GameId(1),
                    weight: 0.5,
                },
                Seed {
                    appid: GameId(2),
                    weight: 0.5,
                },
            ],
            lane_weights: LaneWeights {
                mechanics: 1.0,
                narrative: 0.0,
                vibe: 0.0,
                structure_loop: 0.0,
            },
            include: vec![],
            exclude: vec![],
            text: None,
        };
        let result = graph.retrieve(&intent, 10);
        assert_eq!(result.candidates.len(), 1);
        assert_eq!(result.candidates[0].lanes.mechanics, 0.5);
        assert_eq!(result.candidates[0].concepts, ["cozy", "crafting"]);
    }

    #[test]
    fn graph_does_not_truncate_candidates_before_scoring() {
        let graph = ImmutableGraph::from_envelope(envelope(vec![GraphRecord {
            source_appid: GameId(1),
            candidates: vec![candidate(2), candidate(99)],
        }]))
        .unwrap();
        let intent = NormalizedIntent {
            seeds: vec![Seed {
                appid: GameId(1),
                weight: 1.0,
            }],
            lane_weights: LaneWeights {
                mechanics: 1.0,
                narrative: 0.0,
                vibe: 0.0,
                structure_loop: 0.0,
            },
            include: vec![],
            exclude: vec![],
            text: None,
        };

        let result = graph.retrieve(&intent, 1);

        assert_eq!(
            result
                .candidates
                .iter()
                .map(|candidate| candidate.game_id)
                .collect::<Vec<_>>(),
            [GameId(2), GameId(99)]
        );
    }

    #[test]
    fn rejects_bad_lanes_duplicate_sources_and_candidates() {
        let mut bad_lanes = envelope(vec![]);
        bad_lanes.lanes[3] = Lane::Vibe;
        assert_eq!(
            ImmutableGraph::from_envelope(bad_lanes).unwrap_err(),
            GraphError::InvalidLanes
        );
        let duplicate_source = envelope(vec![
            GraphRecord {
                source_appid: GameId(1),
                candidates: vec![],
            },
            GraphRecord {
                source_appid: GameId(1),
                candidates: vec![],
            },
        ]);
        assert_eq!(
            ImmutableGraph::from_envelope(duplicate_source).unwrap_err(),
            GraphError::DuplicateSource(GameId(1))
        );
        let duplicate_candidate = envelope(vec![GraphRecord {
            source_appid: GameId(1),
            candidates: vec![candidate(2), candidate(2)],
        }]);
        assert_eq!(
            ImmutableGraph::from_envelope(duplicate_candidate).unwrap_err(),
            GraphError::DuplicateCandidate {
                source_appid: GameId(1),
                candidate: GameId(2)
            }
        );
    }
}
