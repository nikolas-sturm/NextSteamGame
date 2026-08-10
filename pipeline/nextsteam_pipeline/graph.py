from __future__ import annotations

from bisect import bisect_left

from .models import LANES, CanonicalGame, Edge, Lane


def build_candidate_graph(
    games: list[CanonicalGame], fallback_neighbors: int = 50, max_neighbors: int = 500
) -> list[Edge]:
    if fallback_neighbors < 0 or max_neighbors <= 0:
        raise ValueError("fallback_neighbors must be non-negative and max_neighbors positive")
    ordered = sorted(games, key=lambda game: (game.owners_midpoint, game.appid))
    concepts: dict[tuple[Lane, str], list[CanonicalGame]] = {}
    developers: dict[str, list[CanonicalGame]] = {}
    publishers: dict[str, list[CanonicalGame]] = {}
    for game in ordered:
        for lane in LANES:
            for concept in game.lanes[lane]:
                concepts.setdefault((lane, concept), []).append(game)
        if game.developer:
            developers.setdefault(game.developer, []).append(game)
        if game.publisher:
            publishers.setdefault(game.publisher, []).append(game)

    edges: list[Edge] = []
    for left in sorted(games, key=lambda game: game.appid):
        pool: dict[int, CanonicalGame] = {}
        for lane in LANES:
            for concept in left.lanes[lane]:
                for candidate in _nearby(concepts[(lane, concept)], left, max_neighbors):
                    pool[candidate.appid] = candidate
        for group in (developers.get(left.developer, []), publishers.get(left.publisher, [])):
            for candidate in _nearby(group, left, max_neighbors):
                pool[candidate.appid] = candidate
        for candidate in _nearby(ordered, left, fallback_neighbors):
            pool[candidate.appid] = candidate
        pool.pop(left.appid, None)

        ranked: list[tuple[float, float, float, int, Edge]] = []
        for right in pool.values():
            similarities, matched, same_identity, niche_proximity = _candidate_metrics(left, right)
            reasons = [f"lane:{lane}" for lane in LANES if matched[lane]]
            features = {
                "identity": float(same_identity),
                "niche_proximity": niche_proximity,
            }
            if same_identity:
                reasons.append("identity")
            if niche_proximity >= 0.75:
                reasons.append("niche")
            if not reasons:
                reasons.append("fallback")
            edge = _edge(left, right, reasons, similarities, matched, features)
            ranked.append(
                (
                    -sum(similarities.values()),
                    -features["identity"],
                    -niche_proximity,
                    right.appid,
                    edge,
                )
            )
        ranked.sort(key=lambda item: item[:4])
        edges.extend(item[4] for item in ranked[:max_neighbors])
    return sorted(edges, key=lambda edge: (edge.source_appid, edge.target_appid))


def candidate_rank_key(
    source: CanonicalGame, candidate: CanonicalGame
) -> tuple[float, float, float, int]:
    similarities, _, same_identity, niche_proximity = _candidate_metrics(source, candidate)
    return -sum(similarities.values()), -float(same_identity), -niche_proximity, candidate.appid


def _candidate_metrics(
    left: CanonicalGame, right: CanonicalGame
) -> tuple[dict[Lane, float], dict[Lane, tuple[str, ...]], bool, float]:
    similarities: dict[Lane, float] = {}
    matched: dict[Lane, tuple[str, ...]] = {}
    for lane in LANES:
        shared = set(left.lanes[lane]).intersection(right.lanes[lane])
        union = set(left.lanes[lane]).union(right.lanes[lane])
        similarities[lane] = len(shared) / len(union) if union else 0.0
        matched[lane] = tuple(sorted(shared))
    same_identity = bool(left.developer and left.developer == right.developer) or bool(
        left.publisher and left.publisher == right.publisher
    )
    niche_distance = abs(left.owners_midpoint - right.owners_midpoint) / max(
        1, left.owners_midpoint, right.owners_midpoint
    )
    return similarities, matched, same_identity, 1.0 / (1.0 + niche_distance)


def _nearby(ordered: list[CanonicalGame], game: CanonicalGame, limit: int) -> list[CanonicalGame]:
    if limit == 0 or len(ordered) <= 1:
        return []
    key = (game.owners_midpoint, game.appid)
    position = bisect_left(ordered, key, key=lambda item: (item.owners_midpoint, item.appid))
    window = ordered[max(0, position - limit) : position + limit + 1]
    return sorted(
        (candidate for candidate in window if candidate.appid != game.appid),
        key=lambda candidate: (
            abs(candidate.owners_midpoint - game.owners_midpoint)
            / max(1, candidate.owners_midpoint, game.owners_midpoint),
            candidate.appid,
        ),
    )[:limit]


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
