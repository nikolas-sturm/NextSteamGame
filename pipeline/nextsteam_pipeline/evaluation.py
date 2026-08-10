from __future__ import annotations

from collections.abc import Callable

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
) -> dict[str, object]:
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
            }
        )
    return {"kind": "candidate_graph_size", "reports": reports}
