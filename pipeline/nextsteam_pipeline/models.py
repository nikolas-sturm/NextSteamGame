from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Lane = Literal["mechanics", "narrative", "vibe", "structure_loop"]
LANES: tuple[Lane, ...] = ("mechanics", "narrative", "vibe", "structure_loop")


@dataclass(frozen=True)
class Provenance:
    source: str
    upstream_id: str
    fetched_at: str
    url: str
    payload_sha256: str


@dataclass(frozen=True)
class RawGame:
    appid: int
    name: str
    description: str
    tags: tuple[str, ...]
    genres: tuple[str, ...]
    developer: str
    publisher: str
    positive: int
    negative: int
    owners: str
    provenance: tuple[Provenance, ...]
    release_year: int | None = None
    header_image_url: str | None = None


@dataclass(frozen=True)
class ReviewEvidence:
    evidence_id: str
    appid: int
    review_id: str
    text: str
    recommended: bool
    playtime_minutes: int
    provenance: Provenance


@dataclass(frozen=True)
class InterpretedEvidence:
    evidence_id: str
    appid: int
    lane: Lane
    value: str
    confidence: float
    source_evidence_ids: tuple[str, ...]
    model: dict[str, str]
    excerpt: str


@dataclass(frozen=True)
class CanonicalGame:
    appid: int
    name: str
    short_description: str
    release_year: int | None
    header_image_url: str | None
    steam_url: str
    developer: str
    publisher: str
    lanes: dict[Lane, tuple[str, ...]]
    lane_evidence_ids: dict[Lane, tuple[str, ...]]
    evidence_ids: tuple[str, ...]
    mapping_version: str
    score: float
    owners_midpoint: int


@dataclass(frozen=True)
class Edge:
    source_appid: int
    target_appid: int
    reasons: tuple[str, ...]
    lane_similarities: dict[Lane, float]
    matched_concepts: dict[Lane, tuple[str, ...]]
    features: dict[str, float]
    evidence_ids: tuple[str, ...]


@dataclass
class StageManifest:
    stage: str
    version: str
    status: Literal["running", "complete", "failed"]
    input_checksums: dict[str, str] = field(default_factory=dict)
    output_checksums: dict[str, str] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
