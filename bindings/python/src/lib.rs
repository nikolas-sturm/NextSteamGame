use domain::{CandidateFeatures, RecommendationRequest};
use pyo3::{exceptions::PyValueError, prelude::*};

fn rank_payload(request_json: &str, candidates_json: &str) -> Result<String, String> {
    let request: RecommendationRequest =
        serde_json::from_str(request_json).map_err(|error| error.to_string())?;
    let candidates: Vec<CandidateFeatures> =
        serde_json::from_str(candidates_json).map_err(|error| error.to_string())?;
    let normalized = recommendation_core::normalize(&request.seeds, &request.intent)
        .map_err(|error| error.to_string())?;
    let ranked = recommendation_core::rank(&normalized, candidates, request.limit)
        .map_err(|error| error.to_string())?;
    serde_json::to_string(&serde_json::json!({
        "normalized_intent": normalized,
        "results": ranked,
    }))
    .map_err(|error| error.to_string())
}

#[pyfunction]
fn rank_json(request_json: &str, candidates_json: &str) -> PyResult<String> {
    rank_payload(request_json, candidates_json).map_err(PyValueError::new_err)
}

#[pymodule]
fn nextsteam_core(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(rank_json, module)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn binding_payload_uses_rust_normalization_and_ranking() {
        let request = r#"{
            "seeds":[{"appid":1,"weight":1.0}],
            "intent":{"lane_weights":{"mechanics":1.0,"narrative":0.0,"vibe":0.0,"structure_loop":0.0},"include":[],"exclude":[],"text":null},
            "limit":1
        }"#;
        let candidates = r#"[
            {"game_id":2,"lanes":{"mechanics":0.2,"narrative":0.0,"vibe":0.0,"structure_loop":0.0},"concepts":[],"evidence_ids":[]},
            {"game_id":3,"lanes":{"mechanics":0.9,"narrative":0.0,"vibe":0.0,"structure_loop":0.0},"concepts":[],"evidence_ids":[]}
        ]"#;

        let output: serde_json::Value =
            serde_json::from_str(&rank_payload(request, candidates).unwrap()).unwrap();

        assert_eq!(output["results"][0]["game_id"], 3);
        assert_eq!(
            output["normalized_intent"]["lane_weights"]["mechanics"],
            1.0
        );
    }
}
