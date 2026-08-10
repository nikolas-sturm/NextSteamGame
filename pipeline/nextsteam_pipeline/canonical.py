from __future__ import annotations

from collections import defaultdict

from .models import LANES, CanonicalGame, InterpretedEvidence, Lane, RawGame

MAPPING_VERSION = "2026-08-10"
MAPPINGS: dict[Lane, dict[str, str]] = {
    "mechanics": {"building": "crafting"},
    "narrative": {"sci_fi": "space_opera"},
    "vibe": {"relaxing": "cozy", "hardcore": "challenging"},
    "structure_loop": {"coop": "co_op", "co-op": "co_op"},
}


def owners_midpoint(value: str) -> int:
    numbers = [int(part.strip().replace(",", "")) for part in value.split("..")]
    return sum(numbers) // len(numbers) if numbers else 0


def canonicalize(game: RawGame, evidence: list[InterpretedEvidence]) -> CanonicalGame:
    lanes: defaultdict[Lane, set[str]] = defaultdict(set)
    lane_evidence: defaultdict[Lane, set[str]] = defaultdict(set)
    for item in evidence:
        lanes[item.lane].add(MAPPINGS[item.lane].get(item.value, item.value))
        lane_evidence[item.lane].add(item.evidence_id)
    total = game.positive + game.negative
    return CanonicalGame(
        appid=game.appid,
        name=game.name.strip(),
        short_description=game.description,
        release_year=game.release_year,
        header_image_url=game.header_image_url,
        steam_url=f"https://store.steampowered.com/app/{game.appid}",
        developer=game.developer.strip().casefold(),
        publisher=game.publisher.strip().casefold(),
        lanes={lane: tuple(sorted(lanes[lane])) for lane in LANES},
        lane_evidence_ids={lane: tuple(sorted(lane_evidence[lane])) for lane in LANES},
        evidence_ids=tuple(sorted(item.evidence_id for item in evidence)),
        mapping_version=MAPPING_VERSION,
        score=game.positive / total if total else 0.0,
        owners_midpoint=owners_midpoint(game.owners),
    )
