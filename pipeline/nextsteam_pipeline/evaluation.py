from __future__ import annotations

from collections.abc import Callable

from .graph import candidate_rank_key
from .models import CanonicalGame, Edge

Metric = Callable[[list[CanonicalGame], list[Edge]], float]


def evaluate(
    games: list[CanonicalGame], edges: list[Edge], metrics: dict[str, Metric]
) -> dict[str, float]:
    return {name: metric(games, edges) for name, metric in metrics.items()}


def graph_coverage(games: list[CanonicalGame], edges: list[Edge]) -> float:
    covered = {edge.source_appid for edge in edges}.union(edge.target_appid for edge in edges)
    return len(covered) / len(games) if games else 1.0


def candidate_graph_size_report(
    games: list[CanonicalGame],
    builder: Callable[[list[CanonicalGame]], list[Edge]],
    sizes: tuple[int, ...] = (500, 1000, 2000),
    k: int = 10,
) -> dict[str, object]:
    if k <= 0:
        raise ValueError("k must be positive")
    reports = []
    for requested in sizes:
        sample = sorted(games, key=lambda game: game.appid)[:requested]
        edges = builder(sample)
        reports.append(
            {
                "requested_games": requested,
                "actual_games": len(sample),
                "edges": len(edges),
                "edges_per_game": len(edges) / len(sample) if sample else 0.0,
                "recall_at_k": _candidate_recall(sample, edges, k),
                "k": k,
            }
        )
    return {"kind": "candidate_graph_recall", "reports": reports}


def _candidate_recall(games: list[CanonicalGame], edges: list[Edge], k: int) -> float:
    if len(games) <= 1:
        return 1.0
    found: dict[int, set[int]] = {}
    for edge in edges:
        found.setdefault(edge.source_appid, set()).add(edge.target_appid)
    recalls = []
    for source in games:
        expected = {
            candidate.appid
            for candidate in sorted(
                (candidate for candidate in games if candidate.appid != source.appid),
                key=lambda candidate: candidate_rank_key(source, candidate),
            )[:k]
        }
        recalls.append(len(expected.intersection(found.get(source.appid, set()))) / len(expected))
    return sum(recalls) / len(recalls)
