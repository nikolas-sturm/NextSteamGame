use std::{
    collections::BTreeMap,
    fs,
    path::{Component, Path, PathBuf},
};

use domain::{API_COMPATIBILITY_VERSION, ARTIFACT_SCHEMA_VERSION, BuildId, Evidence, Game, GameId};
use retrieval::ImmutableGraph;
use serde::{Deserialize, Serialize, de::DeserializeOwned};
use serde_json::Value;
use sha2::{Digest, Sha256};
use thiserror::Error;

const RUNTIME_FILES: [&str; 3] = ["metadata.json", "graph.json", "evidence.json"];

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Manifest {
    pub build_id: BuildId,
    pub created_at: String,
    pub artifact_schema_version: u32,
    pub api_compatibility_version: u32,
    pub source_git_sha: String,
    pub pipeline_git_sha: String,
    pub acquisition_windows: BTreeMap<String, Value>,
    pub models: Vec<BTreeMap<String, Value>>,
    pub ontology_version: String,
    pub scorer_version: String,
    pub counts: ArtifactCounts,
    pub checksums: BTreeMap<String, String>,
    pub evaluation_report_id: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ArtifactCounts {
    pub games: usize,
    pub edges: usize,
    pub evidence: usize,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct MetadataEnvelope {
    build_id: BuildId,
    games: Vec<Game>,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct EvidenceEnvelope {
    build_id: BuildId,
    evidence: Vec<Evidence>,
}

pub struct ArtifactStore {
    pub root: PathBuf,
    pub manifest: Manifest,
    pub metadata: BTreeMap<GameId, Game>,
    pub evidence: BTreeMap<String, Evidence>,
    pub graph: ImmutableGraph,
}

#[derive(Debug, Error)]
pub enum ArtifactError {
    #[error("artifact I/O failed for {path}: {source}")]
    Io {
        path: PathBuf,
        source: std::io::Error,
    },
    #[error("artifact JSON invalid for {path}: {source}")]
    Json {
        path: PathBuf,
        source: serde_json::Error,
    },
    #[error("unsupported artifact schema version {0}")]
    SchemaVersion(u32),
    #[error("incompatible API version {0}")]
    ApiVersion(u32),
    #[error("manifest field {0} is invalid")]
    InvalidManifest(String),
    #[error("embedded build ID mismatch in {artifact}: expected {expected:?}, found {actual:?}")]
    BuildIdMismatch {
        artifact: &'static str,
        expected: BuildId,
        actual: BuildId,
    },
    #[error("missing checksum for {0}")]
    MissingChecksum(String),
    #[error("checksum mismatch for {0}")]
    ChecksumMismatch(String),
    #[error("unsafe artifact path {0}")]
    UnsafePath(String),
    #[error("artifact count mismatch for {field}: expected {expected}, found {actual}")]
    CountMismatch {
        field: &'static str,
        expected: usize,
        actual: usize,
    },
    #[error("duplicate metadata game ID {0:?}")]
    DuplicateGame(GameId),
    #[error("duplicate evidence ID {0}")]
    DuplicateEvidence(String),
    #[error("graph references missing game {0:?}")]
    MissingGame(GameId),
    #[error("graph references missing evidence {0}")]
    MissingEvidence(String),
    #[error("candidate graph invalid: {0}")]
    Graph(#[from] retrieval::GraphError),
}

impl ArtifactStore {
    pub fn load(root: impl AsRef<Path>) -> Result<Self, ArtifactError> {
        let root = root.as_ref();
        let manifest: Manifest = read_json(&root.join("manifest.json"))?;
        validate_manifest(&manifest)?;
        for (name, expected) in &manifest.checksums {
            let bytes = read_bytes(&root.join(validate_path(name)?))?;
            if hex::encode(Sha256::digest(&bytes)) != *expected {
                return Err(ArtifactError::ChecksumMismatch(name.clone()));
            }
        }
        for file in RUNTIME_FILES {
            if !manifest.checksums.contains_key(file) {
                return Err(ArtifactError::MissingChecksum(file.into()));
            }
        }
        let metadata_envelope: MetadataEnvelope = read_json(&root.join("metadata.json"))?;
        require_build_id(
            "metadata.json",
            &manifest.build_id,
            &metadata_envelope.build_id,
        )?;
        let evidence_envelope: EvidenceEnvelope = read_json(&root.join("evidence.json"))?;
        require_build_id(
            "evidence.json",
            &manifest.build_id,
            &evidence_envelope.build_id,
        )?;
        let graph_file =
            fs::File::open(root.join("graph.json")).map_err(|source| ArtifactError::Io {
                path: root.join("graph.json"),
                source,
            })?;
        let graph = ImmutableGraph::from_reader(graph_file)?;
        require_build_id("graph.json", &manifest.build_id, graph.build_id())?;
        let metadata = unique_metadata(metadata_envelope.games)?;
        let evidence = unique_evidence(evidence_envelope.evidence)?;
        validate_count("games", manifest.counts.games, metadata.len())?;
        validate_count("edges", manifest.counts.edges, graph.edge_count())?;
        validate_count("evidence", manifest.counts.evidence, evidence.len())?;
        if let Some(id) = graph.game_ids().find(|id| !metadata.contains_key(id)) {
            return Err(ArtifactError::MissingGame(id));
        }
        if let Some(id) = graph.evidence_ids().find(|id| !evidence.contains_key(*id)) {
            return Err(ArtifactError::MissingEvidence(id.into()));
        }
        Ok(Self {
            root: root.to_path_buf(),
            manifest,
            metadata,
            evidence,
            graph,
        })
    }
}

fn require_build_id(
    artifact: &'static str,
    expected: &BuildId,
    actual: &BuildId,
) -> Result<(), ArtifactError> {
    if expected != actual {
        return Err(ArtifactError::BuildIdMismatch {
            artifact,
            expected: expected.clone(),
            actual: actual.clone(),
        });
    }
    Ok(())
}

fn validate_manifest(manifest: &Manifest) -> Result<(), ArtifactError> {
    if manifest.artifact_schema_version != ARTIFACT_SCHEMA_VERSION {
        return Err(ArtifactError::SchemaVersion(
            manifest.artifact_schema_version,
        ));
    }
    if manifest.api_compatibility_version != API_COMPATIBILITY_VERSION {
        return Err(ArtifactError::ApiVersion(
            manifest.api_compatibility_version,
        ));
    }
    if manifest.build_id.0.is_empty() || manifest.build_id.0.len() > 128 {
        return Err(ArtifactError::InvalidManifest("build_id".into()));
    }
    if manifest.created_at.is_empty()
        || manifest.source_git_sha.is_empty()
        || manifest.pipeline_git_sha.is_empty()
        || manifest.ontology_version.is_empty()
        || manifest.scorer_version.is_empty()
        || manifest.evaluation_report_id.is_empty()
    {
        return Err(ArtifactError::InvalidManifest("provenance".into()));
    }
    if manifest.checksums.is_empty()
        || manifest.checksums.values().any(|value| {
            value.len() != 64
                || !value
                    .bytes()
                    .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
        })
    {
        return Err(ArtifactError::InvalidManifest("checksums".into()));
    }
    Ok(())
}

fn validate_path(name: &str) -> Result<&Path, ArtifactError> {
    let path = Path::new(name);
    if path.is_absolute()
        || path
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
    {
        return Err(ArtifactError::UnsafePath(name.into()));
    }
    Ok(path)
}
fn validate_count(
    field: &'static str,
    expected: usize,
    actual: usize,
) -> Result<(), ArtifactError> {
    if expected != actual {
        return Err(ArtifactError::CountMismatch {
            field,
            expected,
            actual,
        });
    }
    Ok(())
}
fn read_bytes(path: &Path) -> Result<Vec<u8>, ArtifactError> {
    fs::read(path).map_err(|source| ArtifactError::Io {
        path: path.into(),
        source,
    })
}
fn read_json<T: DeserializeOwned>(path: &Path) -> Result<T, ArtifactError> {
    serde_json::from_slice(&read_bytes(path)?).map_err(|source| ArtifactError::Json {
        path: path.into(),
        source,
    })
}
fn unique_metadata(items: Vec<Game>) -> Result<BTreeMap<GameId, Game>, ArtifactError> {
    let mut result = BTreeMap::new();
    for item in items {
        let id = item.appid;
        if result.insert(id, item).is_some() {
            return Err(ArtifactError::DuplicateGame(id));
        }
    }
    Ok(result)
}
fn unique_evidence(items: Vec<Evidence>) -> Result<BTreeMap<String, Evidence>, ArtifactError> {
    let mut result = BTreeMap::new();
    for item in items {
        let id = item.id.clone();
        if result.insert(id.clone(), item).is_some() {
            return Err(ArtifactError::DuplicateEvidence(id));
        }
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    fn manifest(checksums: BTreeMap<String, String>) -> Manifest {
        Manifest {
            build_id: BuildId("test".into()),
            created_at: "2026-08-10T00:00:00Z".into(),
            artifact_schema_version: 1,
            api_compatibility_version: 1,
            source_git_sha: "source".into(),
            pipeline_git_sha: "pipeline".into(),
            acquisition_windows: BTreeMap::new(),
            models: vec![],
            ontology_version: "1".into(),
            scorer_version: "1".into(),
            counts: ArtifactCounts {
                games: 0,
                edges: 0,
                evidence: 0,
            },
            checksums,
            evaluation_report_id: "eval-1".into(),
        }
    }
    fn write_fixture(root: &Path, embedded_build: &str) {
        let files = [
            (
                "metadata.json",
                serde_json::json!({"build_id":embedded_build,"games":[]}),
            ),
            (
                "evidence.json",
                serde_json::json!({"build_id":embedded_build,"evidence":[]}),
            ),
            (
                "graph.json",
                serde_json::json!({"build_id":embedded_build,"lanes":["mechanics","narrative","vibe","structure_loop"],"records":[]}),
            ),
        ];
        let mut checksums = BTreeMap::new();
        for (name, value) in files {
            let bytes = serde_json::to_vec(&value).unwrap();
            fs::write(root.join(name), &bytes).unwrap();
            checksums.insert(name.into(), hex::encode(Sha256::digest(&bytes)));
        }
        fs::write(
            root.join("manifest.json"),
            serde_json::to_vec(&manifest(checksums)).unwrap(),
        )
        .unwrap();
    }

    #[test]
    fn exact_envelopes_load_and_corruption_fails_closed() {
        let root = tempdir().unwrap();
        write_fixture(root.path(), "test");
        assert_eq!(
            ArtifactStore::load(root.path()).unwrap().manifest.build_id,
            BuildId("test".into())
        );
        fs::write(root.path().join("graph.json"), "corrupt").unwrap();
        assert!(
            matches!(ArtifactStore::load(root.path()), Err(ArtifactError::ChecksumMismatch(file)) if file == "graph.json")
        );
    }

    #[test]
    fn embedded_build_mismatch_is_rejected() {
        let root = tempdir().unwrap();
        write_fixture(root.path(), "other");
        assert!(matches!(
            ArtifactStore::load(root.path()),
            Err(ArtifactError::BuildIdMismatch {
                artifact: "metadata.json",
                ..
            })
        ));
    }

    #[test]
    fn corrupt_manifest_is_rejected() {
        let root = tempdir().unwrap();
        fs::write(root.path().join("manifest.json"), br#"{"build_id":"x"}"#).unwrap();
        assert!(matches!(
            ArtifactStore::load(root.path()),
            Err(ArtifactError::Json { .. })
        ));
    }
}
