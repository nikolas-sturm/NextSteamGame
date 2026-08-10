from __future__ import annotations

from itertools import combinations

from .models import LANES, CanonicalGame, Edge, Lane


def build_candidate_graph(games: list[CanonicalGame], fallback_neighbors: int = 2) -> list[Edge]:
    edges: list[Edge] = []
    for left, right in combinations(sorted(games, key=lambda game: game.appid), 2):
        similarities: dict[Lane, float] = {}
        concepts: dict[Lane, tuple[str, ...]] = {}
        reasons: list[str] = []
        for lane in LANES:
            shared = set(left.lanes[lane]).intersection(right.lanes[lane])
            union = set(left.lanes[lane]).union(right.lanes[lane])
            similarities[lane] = len(shared) / len(union) if union else 0.0
            concepts[lane] = tuple(sorted(shared))
            if shared:
                reasons.append(f"lane:{lane}")
        same_identity = left.developer == right.developer or left.publisher == right.publisher
        niche_distance = abs(left.owners_midpoint - right.owners_midpoint) / max(
            1, left.owners_midpoint, right.owners_midpoint
        )
        features = {
            "identity": float(same_identity),
            "niche_proximity": 1.0 / (1.0 + niche_distance),
        }
        if same_identity:
            reasons.append("identity")
        if features["niche_proximity"] >= 0.75:
            reasons.append("niche")
        if reasons:
            edges.extend(
                (
                    _edge(left, right, reasons, similarities, concepts, features),
                    _edge(right, left, reasons, similarities, concepts, features),
                )
            )
    existing = {(edge.source_appid, edge.target_appid) for edge in edges}
    for game in games:
        nearest = sorted(
            (other for other in games if other.appid != game.appid),
            key=lambda other: (abs(game.owners_midpoint - other.owners_midpoint), other.appid),
        )[:fallback_neighbors]
        for other in nearest:
            key = (game.appid, other.appid)
            if key not in existing:
                edges.append(
                    _edge(
                        game,
                        other,
                        ["fallback"],
                        {lane: 0.0 for lane in LANES},
                        {lane: () for lane in LANES},
                        {"fallback_rank": 1.0},
                    )
                )
                existing.add(key)
    return sorted(edges, key=lambda edge: (edge.source_appid, edge.target_appid))


def _edge(
    left: CanonicalGame,
    right: CanonicalGame,
    reasons: list[str],
    similarities: dict[Lane, float],
    concepts: dict[Lane, tuple[str, ...]],
    features: dict[str, float],
) -> Edge:
    relevant_ids: set[str] = set()
    for lane in LANES:
        if concepts[lane]:
            relevant_ids.update(left.lane_evidence_ids[lane])
            relevant_ids.update(right.lane_evidence_ids[lane])
    return Edge(
        left.appid,
        right.appid,
        tuple(sorted(reasons)),
        similarities,
        concepts,
        features,
        tuple(sorted(relevant_ids)),
    )
