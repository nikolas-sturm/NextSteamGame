use std::collections::{BTreeMap, BTreeSet};

use domain::{
    CandidateFeatures, Lane, LaneWeights, NormalizedIntent, RankedCandidate, ScoreContribution,
};
use thiserror::Error;

const CONCEPT_BOOST: f64 = 0.1;

#[derive(Debug, Error, PartialEq)]
pub enum ScoreError {
    #[error("intent must contain at least one positive lane weight")]
    EmptyWeights,
    #[error("weights and candidate values must be finite and within supported ranges")]
    InvalidNumber,
}

pub fn normalize(
    seeds: &[domain::Seed],
    intent: &domain::IntentInput,
) -> Result<NormalizedIntent, ScoreError> {
    if seeds
        .iter()
        .any(|seed| !seed.weight.is_finite() || seed.weight <= 0.0 || seed.weight > 2.0)
        || intent
            .lane_weights
            .iter()
            .iter()
            .any(|(_, value)| !value.is_finite() || *value < 0.0 || *value > 2.0)
    {
        return Err(ScoreError::InvalidNumber);
    }
    let seed_total: f64 = seeds.iter().map(|seed| seed.weight).sum();
    let lane_total: f64 = intent
        .lane_weights
        .iter()
        .iter()
        .map(|(_, value)| value)
        .sum();
    if !seed_total.is_finite() || !lane_total.is_finite() || lane_total <= 0.0 {
        return Err(ScoreError::EmptyWeights);
    }
    let combined = seeds.iter().fold(BTreeMap::new(), |mut values, seed| {
        *values.entry(seed.appid).or_insert(0.0) += seed.weight;
        values
    });
    let normalized_seeds = combined
        .into_iter()
        .map(|(appid, weight)| domain::Seed {
            appid,
            weight: weight / seed_total,
        })
        .collect();
    let clean = |items: &[String]| {
        let mut values: Vec<_> = items
            .iter()
            .map(|value| value.trim().to_lowercase())
            .filter(|value| !value.is_empty())
            .collect();
        values.sort();
        values.dedup();
        values
    };
    Ok(NormalizedIntent {
        seeds: normalized_seeds,
        lane_weights: LaneWeights {
            mechanics: intent.lane_weights.mechanics / lane_total,
            narrative: intent.lane_weights.narrative / lane_total,
            vibe: intent.lane_weights.vibe / lane_total,
            structure_loop: intent.lane_weights.structure_loop / lane_total,
        },
        include: clean(&intent.include),
        exclude: clean(&intent.exclude),
        text: intent
            .text
            .as_ref()
            .map(|value| value.trim().to_owned())
            .filter(|value| !value.is_empty()),
    })
}

pub fn rank(
    intent: &NormalizedIntent,
    candidates: impl IntoIterator<Item = CandidateFeatures>,
    limit: usize,
) -> Result<Vec<RankedCandidate>, ScoreError> {
    let seeds: BTreeSet<_> = intent.seeds.iter().map(|seed| seed.appid).collect();
    let excluded: BTreeSet<_> = intent.exclude.iter().map(String::as_str).collect();
    let included: BTreeSet<_> = intent.include.iter().map(String::as_str).collect();
    let mut results = Vec::new();
    for candidate in candidates {
        if seeds.contains(&candidate.game_id)
            || candidate
                .concepts
                .iter()
                .any(|value| excluded.contains(value.as_str()))
        {
            continue;
        }
        if candidate
            .lanes
            .iter()
            .iter()
            .any(|(_, value)| !value.is_finite() || *value < 0.0)
        {
            return Err(ScoreError::InvalidNumber);
        }
        let mut contributions = Vec::with_capacity(4 + included.len());
        let mut missing_lanes = Vec::new();
        for (lane, weight) in intent.lane_weights.iter() {
            let signal = candidate.lanes.get(lane);
            if signal == 0.0 {
                missing_lanes.push(lane);
            }
            let value = weight * signal;
            contributions.push(ScoreContribution {
                key: format!("lane:{lane:?}").to_lowercase(),
                label: lane_label(lane).into(),
                lane: Some(lane),
                value,
                evidence_ids: if value > 0.0 {
                    candidate.evidence_ids.clone()
                } else {
                    Vec::new()
                },
            });
        }
        let matched_concepts: Vec<_> = candidate
            .concepts
            .iter()
            .filter(|value| included.contains(value.as_str()))
            .cloned()
            .collect();
        for concept in &intent.include {
            let matched = matched_concepts.contains(concept);
            contributions.push(ScoreContribution {
                key: format!("concept:{concept}"),
                label: format!("Matches {concept}"),
                lane: None,
                value: if matched { CONCEPT_BOOST } else { 0.0 },
                evidence_ids: if matched {
                    candidate.evidence_ids.clone()
                } else {
                    Vec::new()
                },
            });
        }
        let score = contributions.iter().map(|item| item.value).sum();
        results.push(RankedCandidate {
            game_id: candidate.game_id,
            score,
            contributions,
            matched_concepts,
            missing_lanes,
        });
    }
    results.sort_by(|left, right| {
        right
            .score
            .total_cmp(&left.score)
            .then_with(|| left.game_id.cmp(&right.game_id))
    });
    results.truncate(limit);
    Ok(results)
}

fn lane_label(lane: Lane) -> &'static str {
    match lane {
        Lane::Mechanics => "Mechanics fit",
        Lane::Narrative => "Narrative fit",
        Lane::Vibe => "Vibe fit",
        Lane::StructureLoop => "Structure and loop fit",
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use domain::{GameId, IntentInput, Seed};
    use proptest::prelude::*;

    fn normalized() -> NormalizedIntent {
        normalize(
            &[
                Seed {
                    appid: GameId(9),
                    weight: 2.0,
                },
                Seed {
                    appid: GameId(1),
                    weight: 1.0,
                },
            ],
            &IntentInput {
                lane_weights: LaneWeights {
                    mechanics: 2.0,
                    narrative: 0.0,
                    vibe: 1.0,
                    structure_loop: 0.0,
                },
                include: vec![" Cozy ".into(), "cozy".into()],
                exclude: vec!["HORROR".into()],
                text: None,
            },
        )
        .unwrap()
    }

    #[test]
    fn normalization_is_stable_and_complete_contributions_reconcile() {
        let intent = normalized();
        assert_eq!(intent.seeds[0].appid, GameId(1));
        assert_eq!(intent.include, ["cozy"]);
        let result = rank(
            &intent,
            [CandidateFeatures {
                game_id: GameId(2),
                lanes: LaneWeights {
                    mechanics: 0.8,
                    narrative: 0.0,
                    vibe: 0.5,
                    structure_loop: 0.0,
                },
                concepts: vec!["cozy".into()],
                evidence_ids: vec!["e1".into()],
            }],
            10,
        )
        .unwrap()
        .remove(0);
        assert_eq!(result.contributions.len(), 5);
        assert_eq!(
            result.score,
            result
                .contributions
                .iter()
                .map(|item| item.value)
                .sum::<f64>()
        );
        assert_eq!(result.missing_lanes, [Lane::Narrative, Lane::StructureLoop]);
    }

    proptest! {
        #[test]
        fn ties_are_stable(ids in prop::collection::vec(1u32..1000, 0..100)) {
            let candidates = ids.iter().map(|id| CandidateFeatures { game_id: GameId(*id), lanes: LaneWeights { mechanics: 1.0, narrative: 0.0, vibe: 0.0, structure_loop: 0.0 }, concepts: vec![], evidence_ids: vec![] }).collect::<Vec<_>>();
            let result = rank(&normalized(), candidates, usize::MAX).unwrap();
            prop_assert!(result.windows(2).all(|pair| pair[0].game_id <= pair[1].game_id));
        }
    }
}
