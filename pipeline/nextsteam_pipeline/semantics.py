from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from .models import InterpretedEvidence, Lane, RawGame, ReviewEvidence
from .util import stable_id

LANE_TERMS: dict[Lane, dict[str, tuple[str, ...]]] = {
    "mechanics": {
        "crafting": ("craft", "crafting", "build", "building"),
        "combat": ("combat", "fight", "fighting"),
        "exploration": ("explore", "exploration", "discover"),
    },
    "narrative": {
        "space_opera": ("space", "planet", "galaxy"),
        "fantasy": ("magic", "dragon", "wizard"),
        "mystery": ("mystery", "detective", "investigate"),
    },
    "vibe": {
        "cozy": ("cozy", "relax", "relaxing"),
        "challenging": ("hardcore", "difficult", "challenging"),
        "dark": ("dark", "grim", "horror"),
    },
    "structure_loop": {
        "solo": ("single-player", "solo"),
        "co_op": ("co-op", "cooperative"),
        "run_based": ("roguelike", "run-based", "runs"),
    },
}


class SemanticAdapter(Protocol):
    @property
    def metadata(self) -> dict[str, str]: ...

    def interpret(
        self, game: RawGame, reviews: list[ReviewEvidence]
    ) -> list[InterpretedEvidence]: ...


@dataclass(frozen=True)
class DeterministicBaseline:
    version: str = "2.0.0"

    @property
    def metadata(self) -> dict[str, str]:
        return {"kind": "keyword-baseline", "name": "deterministic-local", "version": self.version}

    def interpret(self, game: RawGame, reviews: list[ReviewEvidence]) -> list[InterpretedEvidence]:
        sources = [
            ("store", game.description),
            *((review.evidence_id, review.text) for review in reviews),
        ]
        values: list[InterpretedEvidence] = []
        for lane, concepts in LANE_TERMS.items():
            for concept, terms in concepts.items():
                matching = [
                    (source_id, text)
                    for source_id, text in sources
                    if set(re.findall(r"[a-z]+(?:-[a-z]+)?", text.lower())).intersection(terms)
                ]
                if not matching:
                    continue
                source_ids = tuple(source_id for source_id, _ in matching)
                excerpt = matching[0][1][:500]
                values.append(
                    InterpretedEvidence(
                        evidence_id=stable_id("semantic", game.appid, lane, concept, self.version),
                        appid=game.appid,
                        lane=lane,
                        value=concept,
                        confidence=min(1.0, 0.6 + 0.1 * len(matching)),
                        source_evidence_ids=source_ids,
                        model=self.metadata,
                        excerpt=excerpt,
                    )
                )
        return values


class ClassifierAdapter(Protocol):
    @property
    def metadata(self) -> dict[str, str]: ...

    def classify(self, texts: list[str], lane: Lane) -> list[dict[str, float]]: ...


class EmbeddingAdapter(Protocol):
    @property
    def metadata(self) -> dict[str, str]: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...
