use std::{
    collections::{BTreeMap, BTreeSet},
    io::Read,
    sync::Arc,
};

use domain::{
    BuildId, CandidateFeatures, GameId, Lane, LaneWeights, NormalizedIntent, RetrievalMode,
    RetrievalState,
};
use serde::{Deserialize, Serialize};
use thiserror::Error;

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
    fn retrieve(&self, intent: &NormalizedIntent, limit: usize) -> Retrieval {
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
        candidates.truncate(limit);
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
